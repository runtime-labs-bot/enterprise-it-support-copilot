from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.api.main import app
from app.agent.graph import save_response
from app.agent.state import AgentState
from app.services.conversation_history import ConversationHistory


class ConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "history.sqlite"
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.agent = self.make_agent(self.connection)
        self.history = ConversationHistory(self.agent, self.path)
        self.agent_patch = patch("app.api.main.agent", self.agent)
        self.history_patch = patch("app.api.main.history", self.history)
        self.agent_patch.start()
        self.history_patch.start()
        def identity(path, **kwargs):
            token = kwargs.get("authorization", "")
            if token == "Bearer revoked":
                raise HTTPException(status_code=401, detail="Revoked")
            user_id = 2 if token == "Bearer second-user" else 1
            return {"id": user_id, "employee_id": user_id + 30, "role": "employee"}
        self.identity_patch = patch("app.api.main.backend_request", side_effect=identity)
        self.identity_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.identity_patch.stop()
        self.history_patch.stop()
        self.agent_patch.stop()
        self.connection.close()
        self.directory.cleanup()

    def make_agent(self, connection):
        def respond(state):
            result = {"answer": "Reply to " + state["question"], "sources": [{"document": "Test guide"}], "status": "answered"}
            return {**result, **save_response(result)}
        workflow = StateGraph(AgentState)
        workflow.add_node("respond", respond)
        workflow.add_edge(START, "respond")
        workflow.add_edge("respond", END)
        return workflow.compile(checkpointer=SqliteSaver(connection))

    def headers(self, token="first-user"):
        return {"Authorization": "Bearer " + token}

    def ask(self, question, thread="saved-thread", token="first-user"):
        response = self.client.post("/ask", json={"question": question, "thread_id": thread}, headers=self.headers(token))
        self.assertEqual(response.status_code, 200, response.text)

    def test_restores_messages_and_sources_after_relogin(self):
        self.ask("My first question")
        self.ask("Follow-up question")
        # A new access credential for the same verified user keeps the same scope.
        response = self.client.get("/conversations/saved-thread", headers=self.headers("rotated-token"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        messages = response.json()["messages"]
        self.assertEqual([row["role"] for row in messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual(messages[0]["content"], "My first question")
        self.assertEqual(messages[1]["sources"], [{"document": "Test guide"}])
        self.assertEqual(messages[1]["status"], "answered")

    def test_saved_history_survives_new_connection(self):
        self.ask("Saved before restart")
        self.connection.close()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        restored_agent = self.make_agent(self.connection)
        restored = ConversationHistory(restored_agent, self.path)
        self.assertEqual(restored.get("user:1", "saved-thread")["messages"][0]["content"], "Saved before restart")

    def test_other_user_cannot_list_or_read_conversation(self):
        self.ask("First user's private question")
        response = self.client.get("/conversations", headers=self.headers("second-user"))
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(self.client.get("/conversations/saved-thread", headers=self.headers("second-user")).status_code, 404)
        self.ask("Second user's question", token="second-user")
        response = self.client.get("/conversations/saved-thread", headers=self.headers("second-user"))
        self.assertEqual(response.json()["messages"][0]["content"], "Second user's question")
        self.assertNotIn("First user's private question", response.text)

    def test_order_pagination_and_authentication(self):
        self.ask("Older chat", thread="older")
        self.ask("Latest chat", thread="latest")
        response = self.client.get("/conversations", params={"limit": 1}, headers=self.headers())
        self.assertEqual(response.json()["items"][0]["thread_id"], "latest")
        self.assertEqual(response.json()["next_offset"], 1)
        next_page = self.client.get("/conversations", params={"limit": 1, "offset": 1}, headers=self.headers()).json()
        self.assertEqual(next_page["items"][0]["title"], "Older chat")
        self.assertIsNone(next_page["next_offset"])
        for path in ("/conversations", "/conversations/older"):
            self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.client.get(path, headers=self.headers("revoked")).status_code, 401)

    def test_rename_search_archive_restore_preserve_transcript(self):
        self.ask("Original prompt")
        original = self.client.get("/conversations/saved-thread", headers=self.headers()).json()["messages"]
        renamed = self.client.patch("/conversations/saved-thread", json={"title": "VPN troubleshooting"}, headers=self.headers())
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["title"], "VPN troubleshooting")
        self.assertEqual(renamed.json()["messages"], original)
        matches = self.client.get("/conversations", params={"query": "vpn"}, headers=self.headers()).json()
        self.assertEqual(matches["items"][0]["title"], "VPN troubleshooting")
        self.assertEqual(self.client.get("/conversations", params={"query": "unrelated"}, headers=self.headers()).json()["items"], [])
        self.assertEqual(self.client.patch("/conversations/saved-thread", json={"archived": True}, headers=self.headers()).status_code, 200)
        self.assertEqual(self.client.get("/conversations", headers=self.headers()).json()["items"], [])
        archived = self.client.get("/conversations", params={"archived": True}, headers=self.headers()).json()["items"]
        self.assertEqual(archived[0]["thread_id"], "saved-thread")
        self.assertEqual(self.client.post("/ask", json={"question": "Blocked", "thread_id": "saved-thread"}, headers=self.headers()).status_code, 409)
        restored = self.client.patch("/conversations/saved-thread", json={"archived": False}, headers=self.headers())
        self.assertEqual(restored.json()["messages"], original)
        self.ask("Continue restored chat")
        self.assertEqual(len(self.client.get("/conversations/saved-thread", headers=self.headers()).json()["messages"]), 4)

    def test_metadata_changes_require_owner_and_valid_input(self):
        self.ask("Private chat")
        for change in ({"title": "Hijacked"}, {"archived": True}):
            self.assertEqual(self.client.patch("/conversations/saved-thread", json=change, headers=self.headers("second-user")).status_code, 404)
        for change in ({"title": " "}, {"title": "x" * 81}, {"archived": None}, {}, {"owner": "second-user"}):
            self.assertEqual(self.client.patch("/conversations/saved-thread", json=change, headers=self.headers()).status_code, 422)
        saved = self.client.get("/conversations/saved-thread", headers=self.headers()).json()
        self.assertEqual(saved["title"], "Private chat")
        self.assertFalse(saved["archived"])
