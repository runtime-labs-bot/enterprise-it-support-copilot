import unittest
from unittest.mock import AsyncMock, patch
import httpx
from sqlalchemy.exc import SQLAlchemyError
from mcp.server.fastmcp.exceptions import ToolError
import test_auth
from app.mcp_server import _request


class EvaluationAccessTests(unittest.TestCase):
    setUp = test_auth.AuthenticationTests.setUp
    tearDown = test_auth.AuthenticationTests.tearDown
    account = test_auth.AuthenticationTests.account
    login = test_auth.AuthenticationTests.login
    headers = test_auth.AuthenticationTests.headers
    ticket = test_auth.AuthenticationTests.ticket

    def test_employee_cannot_spoof_ticket_owner(self):
        tokens = self.login()
        response = self.client.post("/tickets", json={"title": "Owner test", "description": "Fixture", "employee_id": self.other["employee_id"]}, headers=self.headers(tokens))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/tickets", headers=self.headers(tokens)).json(), [])
        ticket_id = self.ticket(self.owner, tokens)
        rows = self.client.get("/tickets", headers=self.headers(tokens)).json()
        self.assertEqual([row["id"] for row in rows], [ticket_id])

    def test_jwt_owner_closes_all_active_states_once(self):
        tokens = self.login()
        for initial in ("open", "in_progress", "resolved"):
            ticket_id = self.ticket(self.owner, tokens)
            if initial != "open":
                self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"status": "in_progress"}, headers=self.admin).status_code, 200)
            if initial == "resolved":
                self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"status": "resolved"}, headers=self.admin).status_code, 200)
            url = f"/tickets/{ticket_id}/close"
            self.assertEqual(self.client.post(url, headers=self.headers(tokens)).status_code, 200)
            self.assertEqual(self.client.post(url, headers=self.headers(tokens)).status_code, 200)
            events = self.client.get(f"/tickets/{ticket_id}/history", headers=self.headers(tokens)).json()
            self.assertEqual(sum(event["new_status"] == "closed" for event in events), 1)
            self.assertEqual(events[-1]["old_status"], initial)
            self.assertEqual(events[-1]["actor_employee_id"], self.owner["employee_id"])

    def test_database_failure_is_service_unavailable_without_connection_details(self):
        with patch("app.main.Session.execute", side_effect=SQLAlchemyError("private connection credentials")):
            response = self.client.get("/health/database")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database unavailable"})


class EvaluationMcpFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_database_unavailability_cannot_confirm_a_write(self):
        client = AsyncMock()
        client.request.return_value = httpx.Response(503, json={"detail": "private database connection string"})
        with patch("app.mcp_server.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            with self.assertRaises(ToolError) as error:
                await _request("POST", "/tickets", body={"title": "Temporary fixture"})
        self.assertIn("check current records before retrying", str(error.exception))
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(client.request.await_count, 1)
