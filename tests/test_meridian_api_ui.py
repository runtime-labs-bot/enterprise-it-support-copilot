"""Login, session refresh, UI/API credential handoff without external requests."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from app.api.main import app


def tokens(access="private-test-access", refresh="private-test-refresh"):
    now = datetime.now(timezone.utc)
    return {"access_token": access, "refresh_token": refresh, "expires_at": (now + timedelta(minutes=15)).isoformat(), "session_expires_at": (now + timedelta(days=7)).isoformat(), "user": {"id": 1, "employee_id": 32, "role": "employee", "full_name": "Test Employee", "email": "employee@example.com"}}


def reply(data=None, status=200):
    response = Mock(status_code=status)
    response.json.return_value = data
    return response


class MeridianApiTests(unittest.TestCase):
    def test_login_role_is_validated_and_forwarded(self):
        with TestClient(app) as client, patch("app.api.main.backend_request", return_value=tokens()) as backend:
            for role in ("employee", "admin"):
                response = client.post("/auth/login", json={"email": "employee@example.com", "password": "Fixture password 2026!", "role": role})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(backend.call_args.kwargs["body"]["role"], role)
            backend.reset_mock()
            self.assertEqual(client.post("/auth/login", json={"email": "employee@example.com", "password": "Fixture password 2026!", "role": "superadmin"}).status_code, 422)
            backend.assert_not_called()
        with TestClient(app) as client, patch("app.api.main.backend_request", side_effect=HTTPException(status_code=403, detail="Wrong login role")):
            self.assertEqual(client.post("/auth/login", json={"email": "employee@example.com", "password": "Fixture password 2026!", "role": "admin"}).status_code, 403)

    def test_validated_identity_runtime_only_and_scoped_threads(self):
        answer = {"answer": "Ticket found", "sources": [], "status": "answered_meridian"}
        identities = [{"id": 1, "employee_id": 32, "role": "employee"}, {"id": 2, "employee_id": 33, "role": "employee"}]
        with TestClient(app) as client, patch("app.api.main.backend_request", side_effect=identities) as backend, patch("app.api.main.agent.invoke", return_value=answer) as invoke:
            payload = {"question": "Show my ticket", "thread_id": "same-public-thread"}
            first = client.post("/ask", json=payload, headers={"Authorization": "Bearer private-test-one"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["thread_id"], "same-public-thread")
            args, kwargs = invoke.call_args
            self.assertEqual(kwargs["context"].employee_api_key, "private-test-one")
            self.assertNotIn("private-test-one", repr(args))
            self.assertNotIn("private-test-one", repr(kwargs["config"]))
            scope_one = kwargs["config"]["configurable"]["thread_id"]
            self.assertEqual(backend.call_args.args[0], "/auth/me")
            client.post("/ask", json=payload, headers={"Authorization": "Bearer private-test-two"})
            self.assertNotEqual(scope_one, invoke.call_args.kwargs["config"]["configurable"]["thread_id"])

    def test_invalid_or_missing_login_never_runs_agent(self):
        with TestClient(app) as client, patch("app.api.main.agent.invoke") as invoke:
            self.assertEqual(client.post("/ask", json={"question": "Hello"}).status_code, 401)
            with patch("app.api.main.backend_request", side_effect=HTTPException(status_code=401, detail="Expired")):
                self.assertEqual(client.post("/ask", json={"question": "Hello"}, headers={"Authorization": "Bearer expired"}).status_code, 401)
            invoke.assert_not_called()

    def test_login_refresh_logout_proxies_are_private(self):
        with TestClient(app) as client, patch("app.api.main.backend_request", return_value=tokens()) as backend:
            response = client.post("/auth/login", json={"email": "employee@example.com", "password": "Fixture password 2026!"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(backend.call_args.kwargs["body"]["password"], "Fixture password 2026!")
            self.assertNotIn("Fixture password 2026!", response.text)
            self.assertEqual(client.post("/auth/refresh", json={"refresh_token": "private-test-refresh"}).status_code, 200)
            self.assertEqual(backend.call_args.args[0], "/auth/refresh")
            backend.return_value = None
            self.assertEqual(client.post("/auth/logout", json={"refresh_token": "private-test-refresh"}).status_code, 204)
            self.assertEqual(backend.call_args.args[0], "/auth/logout")
        with TestClient(app) as client:
            secret = "sensitive" * 30
            response = client.post("/auth/login", json={"email": "employee@example.com", "password": secret})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(secret, response.text)


class MeridianUiTests(unittest.TestCase):
    def setUp(self):
        self.history_mock = patch("requests.get", return_value=reply({"items": [], "next_offset": None}))
        self.history_mock.start()
        self.addCleanup(self.history_mock.stop)

    def page(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"))

    def sign_in(self, page):
        page.run()
        self.assertEqual(len(page.chat_input), 0)
        self.assertEqual([field.label for field in page.text_input], ["Work email", "Password"])
        page.text_input[0].input("employee@example.com")
        page.text_input[1].input("Fixture password 2026!")
        with patch("requests.post", return_value=reply(tokens())) as post:
            page.button[0].click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertTrue(post.call_args.args[0].endswith("/auth/login"))
        self.assertEqual(len(page.chat_input), 1)
        return page

    def test_login_then_chat_uses_bearer_without_keys_or_password(self):
        page = self.sign_in(self.page())
        thread = page.session_state["thread_id"]
        with patch("requests.post", return_value=reply({"answer": "Ticket created", "sources": [], "status": "answered_meridian"})) as post:
            page.chat_input[0].set_value("Create a ticket for my laptop").run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer private-test-access"})
        self.assertEqual(post.call_args.kwargs["json"]["thread_id"], thread)
        self.assertNotIn("private-test-access", repr(page.session_state["messages"]))
        self.assertNotIn("Fixture password 2026!", repr(page.session_state))
        self.assertNotIn("Password", [field.label for field in page.text_input])

    def test_bad_password_stays_on_login(self):
        page = self.page().run()
        page.text_input[0].input("employee@example.com")
        page.text_input[1].input("Wrong password")
        with patch("requests.post", return_value=reply(status=401)):
            page.button[0].click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(len(page.chat_input), 0)
        self.assertEqual(len(page.error), 1)
        self.assertNotIn("auth_session", page.session_state)

    def test_admin_login_opens_dashboard(self):
        page = self.page().run()
        page.radio[0].set_value("Admin login").run()
        page.text_input[0].input("admin@example.com")
        page.text_input[1].input("Fixture password 2026!")
        session = tokens()
        session["user"]["role"] = "admin"
        session["user"]["email"] = "admin@example.com"
        summary = {"employees": {"total": 2, "active": 2}, "devices": {"total": 1, "unassigned": 0}, "tickets": {"open": 1, "in_progress": 0, "resolved": 0, "closed": 0, "high_priority_active": 0}}
        with patch("requests.post", return_value=reply(session)) as post, patch("requests.get", return_value=reply(summary)):
            page.button[0].click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(post.call_args.kwargs["json"]["role"], "admin")
        self.assertEqual(page.sidebar.radio[0].value, "Admin dashboard")
        self.assertEqual(len(page.chat_input), 0)
        self.assertIn("Admin dashboard", [item.value for item in page.header])

    def test_wrong_role_login_does_not_create_ui_session(self):
        page = self.page().run()
        page.radio[0].set_value("Admin login").run()
        page.text_input[0].input("employee@example.com")
        page.text_input[1].input("Fixture password 2026!")
        with patch("requests.post", return_value=reply(status=403)):
            page.button[0].click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertNotIn("auth_session", page.session_state)
        self.assertIn("selected login", page.error[0].value)
        self.assertEqual(len(page.chat_input), 0)

    def test_show_password_toggle(self):
        page = self.page().run()
        self.assertEqual(page.text_input[1].proto.type, 1)
        page.text_input[1].input("Visible fixture password").run()
        page.checkbox[0].check().run()
        self.assertEqual(page.text_input[1].proto.type, 0)
        self.assertEqual(page.text_input[1].value, "Visible fixture password")
        page.checkbox[0].uncheck().run()
        self.assertEqual(page.text_input[1].proto.type, 1)

    def test_latest_chat_restores_after_login_and_can_start_new_chat(self):
        saved = {"thread_id": "earlier-chat", "messages": [{"role": "user", "content": "Earlier question"}, {"role": "assistant", "content": "Saved answer", "sources": []}]}
        def history_reply(url, **kwargs):
            if url.endswith("/earlier-chat"):
                return reply(saved)
            return reply({"items": [{"thread_id": "earlier-chat", "title": "Earlier question"}], "next_offset": None})
        with patch("requests.get", side_effect=history_reply):
            page = self.sign_in(self.page())
            self.assertEqual(page.session_state["thread_id"], "earlier-chat")
            self.assertEqual(page.session_state["messages"], saved["messages"])
            self.assertEqual(len(page.chat_message), 2)
            page.sidebar.button[1].click().run()
            self.assertNotEqual(page.session_state["thread_id"], "earlier-chat")
            self.assertEqual(page.session_state["messages"], [])
            page.sidebar.button[2].click().run()
            self.assertEqual(page.session_state["thread_id"], "earlier-chat")
            self.assertEqual(len(page.chat_message), 2)

    def test_rename_archive_and_restore_controls_preserve_messages(self):
        saved = {"thread_id": "saved-chat", "title": "Original chat", "archived": False, "messages": [{"role": "user", "content": "My question"}, {"role": "assistant", "content": "Saved reply", "sources": []}]}
        def get(url, **kwargs):
            if url.endswith("/saved-chat"):
                return reply(dict(saved))
            archived = kwargs.get("params", {}).get("archived", False)
            items = [{"thread_id": saved["thread_id"], "title": saved["title"], "archived": saved["archived"]}] if archived == saved["archived"] else []
            return reply({"items": items, "next_offset": None})
        def write(method, url, **kwargs):
            saved.update(kwargs["json"])
            return reply(dict(saved))
        page = self.page()
        page.session_state["auth_session"] = tokens()
        with patch("requests.get", side_effect=get), patch("requests.request", side_effect=write):
            page.run()
            next(item for item in page.text_input if item.label == "Conversation name").input("VPN notes")
            next(item for item in page.button if item.label == "Rename chat").click().run()
            self.assertEqual(saved["title"], "VPN notes")
            next(item for item in page.button if item.label == "Archive chat").click().run()
            self.assertTrue(saved["archived"])
            self.assertTrue(page.chat_input[0].proto.disabled)
            next(item for item in page.button if item.label == "Restore chat").click().run()
            self.assertFalse(saved["archived"])
            self.assertFalse(page.chat_input[0].proto.disabled)
            self.assertEqual(page.session_state["messages"], saved["messages"])
            self.assertEqual(len(page.exception), 0)

    def test_access_expiry_refreshes_without_login_form(self):
        page = self.page()
        initial = tokens()
        initial["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        page.session_state["auth_session"] = initial
        with patch("requests.post", return_value=reply(tokens("rotated-access", "rotated-refresh"))) as post:
            page.run()
        self.assertEqual(len(page.exception), 0)
        self.assertTrue(post.call_args.args[0].endswith("/auth/refresh"))
        self.assertEqual(page.session_state["auth_session"]["access_token"], "rotated-access")
        self.assertEqual(len(page.chat_input), 1)
        self.assertNotIn("Password", [field.label for field in page.text_input])

    def test_revoked_refresh_requires_sign_in(self):
        page = self.page()
        initial = tokens()
        initial["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        page.session_state["auth_session"] = initial
        with patch("requests.post", return_value=reply(status=401)):
            page.run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(len(page.chat_input), 0)
        self.assertNotIn("auth_session", page.session_state)

    def test_logout_revokes_and_clears_chat(self):
        page = self.sign_in(self.page())
        page.session_state["messages"] = [{"role": "assistant", "content": "Old conversation"}]
        with patch("requests.post", return_value=reply(status=204)) as post:
            page.sidebar.button[0].click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertTrue(post.call_args.args[0].endswith("/auth/logout"))
        self.assertNotIn("auth_session", page.session_state)
        self.assertNotIn("messages", page.session_state)
        self.assertEqual(len(page.chat_input), 0)
