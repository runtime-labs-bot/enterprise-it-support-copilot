from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from app.api.browser_auth import router, COOKIE_NAME, CSRF_COOKIE
from app.api.main import safe_auth_validation
from app.services.browser_sessions import BrowserSessions
from test_meridian_api_ui import tokens, reply


class BrowserVaultTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sessions.sqlite"
        self.key = Fernet.generate_key()
        self.vault = BrowserSessions(self.path, self.key)

    def test_only_hash_and_encrypted_tokens_are_persisted(self):
        data = tokens()
        handle = self.vault.create(data)
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT * FROM browser_sessions").fetchone()
        for secret in (handle, data["access_token"], data["refresh_token"]):
            self.assertNotIn(secret, repr(row))
        restored_vault = BrowserSessions(self.path, self.key)
        with patch("app.services.browser_sessions.backend_request", return_value={**data["user"], "role": "admin"}):
            restored = restored_vault.restore(handle)
        self.assertEqual(restored["user"]["role"], "admin")
        with self.assertRaises(HTTPException):
            self.vault.restore(handle + "tampered")

    def test_parallel_restore_rotates_once_using_current_refresh(self):
        old = tokens("expired-access", "initial-refresh")
        old["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        handle = self.vault.create(old)
        new = tokens("rotated-access", "rotated-refresh")
        def request(path, **kwargs):
            return new if path == "/auth/refresh" else new["user"]
        with patch("app.services.browser_sessions.backend_request", side_effect=request) as backend:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(self.vault.restore, [handle, handle]))
        self.assertTrue(all(row["access_token"] == "rotated-access" for row in results))
        refreshes = [call for call in backend.call_args_list if call.args[0] == "/auth/refresh"]
        self.assertEqual(len(refreshes), 1)
        self.assertEqual(refreshes[0].kwargs["body"], {"refresh_token": "initial-refresh"})

    def test_revocation_expiry_and_outage_behavior(self):
        handle = self.vault.create(tokens())
        with patch("app.services.browser_sessions.backend_request", side_effect=HTTPException(status_code=503, detail="offline")):
            with self.assertRaises(HTTPException):
                self.vault.restore(handle)
        with patch("app.services.browser_sessions.backend_request", return_value=tokens()["user"]):
            self.vault.restore(handle)
        with patch("app.services.browser_sessions.backend_request", side_effect=HTTPException(status_code=401, detail="revoked")):
            with self.assertRaises(HTTPException):
                self.vault.restore(handle)
        with patch("app.services.browser_sessions.backend_request") as backend, self.assertRaises(HTTPException):
            self.vault.restore(handle)
        backend.assert_not_called()
        expired = tokens()
        expired["session_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with self.assertRaises(HTTPException):
            self.vault.restore(self.vault.create(expired))

    def test_logout_removes_local_session_even_if_backend_unavailable(self):
        handle = self.vault.create(tokens())
        with patch("app.services.browser_sessions.backend_request", side_effect=HTTPException(status_code=503, detail="offline")):
            with self.assertRaises(HTTPException):
                self.vault.revoke(handle)
        with patch("app.services.browser_sessions.backend_request") as backend, self.assertRaises(HTTPException):
            self.vault.restore(handle)
        backend.assert_not_called()


class BrowserRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.vault = BrowserSessions(Path(self.directory.name) / "sessions.sqlite", Fernet.generate_key())
        self.config = patch.dict("os.environ", {"COPILOT_PUBLIC_URL": "http://localhost:8502", "COPILOT_BROWSER_AUTH_URL": "http://localhost:8001/auth/browser", "BROWSER_UI_AUTH_KEY": "private-ui-bridge-fixture"})
        self.config.start()
        self.addCleanup(self.config.stop)
        app = FastAPI()
        app.add_exception_handler(RequestValidationError, safe_auth_validation)
        app.include_router(router)
        self.client = TestClient(app, base_url="http://localhost:8001")
        self.addCleanup(self.client.close)
        self.vault_mock = patch("app.api.browser_auth.vault", return_value=self.vault)
        self.vault_mock.start()
        self.addCleanup(self.vault_mock.stop)

    def login(self):
        form = self.client.get("/auth/browser/login")
        csrf = re.search(r'name="csrf" value="([^"]+)"', form.text).group(1)
        body = {"email": "fixture@example.com", "password": "Fixture password 2026!", "role": "employee", "csrf": csrf}
        with patch("app.api.browser_auth.backend_request", return_value=tokens()):
            response = self.client.post("/auth/browser/login", data=body, headers={"Origin": "http://localhost:8001"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        return response, body

    def test_browser_receives_only_opaque_httponly_cookie_and_clean_redirect(self):
        response, body = self.login()
        self.assertEqual(response.headers["location"], "http://localhost:8502")
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Max-Age=", cookie)
        for secret in (body["password"], tokens()["access_token"], tokens()["refresh_token"]):
            self.assertNotIn(secret, cookie + response.text + response.headers["location"])

    def test_csrf_and_public_restore_are_rejected(self):
        self.client.get("/auth/browser/login")
        body = {"email": "fixture@example.com", "password": "Fixture password 2026!", "role": "admin", "csrf": "x" * 43}
        with patch("app.api.browser_auth.backend_request") as backend:
            self.assertEqual(self.client.post("/auth/browser/login", data=body, headers={"Origin": "http://evil.example"}).status_code, 403)
            self.assertEqual(self.client.post("/auth/browser/login", data=body, headers={"Origin": "http://localhost:8001"}).status_code, 403)
            backend.assert_not_called()
        self.assertEqual(self.client.post("/auth/browser/restore", json={"handle": "x" * 64}).status_code, 403)

    def test_server_restore_and_revoke_reject_cookie_after_logout(self):
        self.login()
        handle = self.client.cookies.get(COOKIE_NAME)
        headers = {"X-UI-Auth-Key": "private-ui-bridge-fixture"}
        with patch("app.services.browser_sessions.backend_request", return_value=tokens()["user"]):
            restored = self.client.post("/auth/browser/restore", json={"handle": handle}, headers=headers)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.headers["cache-control"], "no-store")
        with patch("app.services.browser_sessions.backend_request"):
            self.assertEqual(self.client.post("/auth/browser/revoke", json={"handle": handle}, headers=headers).status_code, 204)
        self.assertEqual(self.client.post("/auth/browser/restore", json={"handle": handle}, headers=headers).status_code, 401)

    def test_https_cookie_is_secure_and_errors_never_echo_credentials(self):
        with patch.dict("os.environ", {"COPILOT_PUBLIC_URL": "https://copilot.example", "COPILOT_BROWSER_AUTH_URL": "https://copilot.example/auth/browser"}):
            response = self.client.get("/auth/browser/login")
            self.assertIn("Secure", response.headers["set-cookie"])
        password = "private-invalid-password" * 20
        response = self.client.post("/auth/browser/login", data={"email": "fixture@example.com", "password": password, "role": "employee", "csrf": "x" * 43})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(password, response.text)


class BrowserUiTests(unittest.TestCase):
    def test_fresh_streamlit_session_restores_from_cookie_without_password(self):
        page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"), default_timeout=10)
        with patch.dict("os.environ", {"COPILOT_BROWSER_AUTH_URL": "http://localhost:8001/auth/browser", "BROWSER_UI_AUTH_KEY": "private-ui-bridge-fixture"}), patch("ui.browser_login.st.context") as context, patch("requests.post", return_value=reply(tokens())) as post, patch("requests.get", return_value=reply({"items": [], "next_offset": None})):
            context.cookies = {COOKIE_NAME: "opaque-browser-fixture-handle"}
            page.run()
        self.assertFalse(page.exception)
        self.assertEqual(len(page.chat_input), 1)
        self.assertTrue(post.call_args.args[0].endswith("/browser/restore"))
        self.assertNotIn("password", post.call_args.kwargs["json"])
        self.assertNotIn("login_password", page.session_state)
