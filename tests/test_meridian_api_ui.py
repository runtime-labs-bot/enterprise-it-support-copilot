"""Verify the UI/API credential handoff without external model requests."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.api.main import app


class MeridianApiTests(unittest.TestCase):
    def test_credential_is_runtime_only_and_threads_are_identity_scoped(self):
        answer = {"answer": "Ticket found", "sources": [], "status": "answered_meridian"}
        with TestClient(app) as client, patch("app.api.main.agent.invoke", return_value=answer) as invoke:
            payload = {"question": "Show my ticket", "thread_id": "same-public-thread"}
            first = client.post("/ask", json=payload, headers={"X-Meridian-Employee-Key": "employee-test-one"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["thread_id"], "same-public-thread")
            args, kwargs = invoke.call_args
            self.assertEqual(kwargs["context"].employee_api_key, "employee-test-one")
            self.assertNotIn("employee-test-one", repr(args))
            self.assertNotIn("employee-test-one", repr(kwargs["config"]))
            scope_one = kwargs["config"]["configurable"]["thread_id"]
            client.post("/ask", json=payload, headers={"X-Meridian-Employee-Key": "employee-test-two"})
            scope_two = invoke.call_args.kwargs["config"]["configurable"]["thread_id"]
            self.assertNotEqual(scope_one, scope_two)


class MeridianUiTests(unittest.TestCase):
    def test_sidebar_key_is_header_and_identity_change_clears_conversation(self):
        page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"))
        page.run()
        self.assertEqual(len(page.exception), 0)
        page.sidebar.text_input[0].input("employee-ui-test-one").run()
        thread_id = page.session_state["thread_id"]
        response = Mock()
        response.json.return_value = {"answer": "Ticket created", "sources": [], "status": "answered_meridian"}
        with patch("requests.post", return_value=response) as post:
            page.chat_input[0].set_value("Create a ticket for my laptop").run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(post.call_args.kwargs["headers"], {"X-Meridian-Employee-Key": "employee-ui-test-one"})
        self.assertEqual(post.call_args.kwargs["json"]["thread_id"], thread_id)
        self.assertNotIn("employee-ui-test-one", repr(post.call_args.kwargs["json"]))
        page.sidebar.text_input[0].input("employee-ui-test-two").run()
        self.assertNotEqual(page.session_state["thread_id"], thread_id)
        self.assertEqual(page.session_state["messages"], [])
