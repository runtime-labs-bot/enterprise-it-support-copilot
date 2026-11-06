import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from app.api.main import app
from test_meridian_api_ui import reply, tokens


class PasswordSetupTests(unittest.TestCase):
    def test_proxy_rejects_role_injection_and_hides_invalid_password(self):
        with TestClient(app) as client, patch("app.api.main.backend_request", return_value=tokens()["user"]) as backend:
            body = {"token": "x" * 64, "password": "A valid fixture password!"}
            response = client.post("/auth/setup-password", json=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(backend.call_args.kwargs["body"], body)
            backend.reset_mock()
            response = client.post("/auth/setup-password", json={**body, "role": "admin"})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(body["password"], response.text)
            self.assertNotIn(body["token"], response.text)
            backend.assert_not_called()

    def test_admin_only_invitation_proxy(self):
        with TestClient(app) as client, patch("app.api.admin.backend_request", return_value=tokens()["user"]) as backend:
            self.assertEqual(client.post("/admin/setup-invitations", json={"employee_id": 32}, headers={"Authorization": "Bearer fixture"}).status_code, 403)
            self.assertEqual(backend.call_count, 1)
            backend.return_value = {**tokens()["user"], "role": "admin"}
            self.assertEqual(client.post("/admin/setup-invitations", json={"employee_id": 32}, headers={"Authorization": "Bearer fixture"}).status_code, 201)
            self.assertEqual(backend.call_args.args[0], "/auth/setup-invitations")

    def test_setup_form_visibility_confirmation_and_completion(self):
        ui = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"), default_timeout=10)
        ui.query_params["setup"] = "x" * 64
        with patch("requests.post", return_value=reply(tokens()["user"])) as post:
            ui.run()
            self.assertFalse(ui.exception)
            self.assertNotIn("setup", ui.query_params)
            ui.text_input(key="setup_password").set_value("A valid fixture password!")
            ui.text_input(key="setup_confirm").set_value("Does not match").run()
            ui.button[0].click().run()
            post.assert_not_called()
            self.assertTrue(ui.error)
            ui.checkbox(key="setup_visible").check().run()
            self.assertEqual(ui.text_input(key="setup_password").proto.type, 0)
            self.assertEqual(ui.text_input(key="setup_password").value, "A valid fixture password!")
            ui.text_input(key="setup_confirm").set_value("A valid fixture password!")
            ui.button[0].click().run()
            self.assertFalse(ui.exception)
            self.assertEqual(post.call_args.args[0].rsplit("/", 1)[1], "setup-password")
            self.assertNotIn("setup_token", ui.session_state)
            self.assertEqual(ui.text_input(key="login_email").value, "employee@example.com")


if __name__ == "__main__":
    unittest.main()
