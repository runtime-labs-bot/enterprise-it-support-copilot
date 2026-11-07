import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from app.api.admin_chat import create_router
from app.agent.meridian import ADMIN_READ_TOOLS, _tool_definitions, run_tool_loop
from app.services.admin_actions import AdminAction, AdminActionStore
from test_meridian import FakeSession, tool_call
from test_meridian_api_ui import reply

PLAN = {"operation": "update_employee", "record_id": 7, "changes": {"is_active": False}}
BEFORE = {"id": 7, "full_name": "Test Employee", "email": "test@example.com", "is_active": True, "updated_at": "2026-11-07T00:00:00Z"}


class AdminActionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "actions.sqlite"
        self.store = AdminActionStore(self.path)

    def propose(self, plan=PLAN):
        with patch("app.services.admin_actions.backend_request", return_value=BEFORE) as request:
            action = self.store.propose("user:1", "thread", plan, "Bearer fixture")
        if plan.get("record_id"):
            self.assertEqual(request.call_args.kwargs.get("method", "GET"), "GET")
        return action

    def test_no_mutation_before_confirmation_and_confirmation_executes_once(self):
        action = self.propose()
        with patch("app.services.admin_actions.backend_request", side_effect=[BEFORE, {**BEFORE, "is_active": False}]) as request:
            result = self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
            duplicate = self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
        self.assertFalse(result["result"]["record"]["is_active"])
        self.assertEqual(result, duplicate)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs["method"], "PATCH")
        self.assertEqual(request.call_args.kwargs["body"], {"is_active": False})
        self.assertEqual(self.store.list("user:1", "thread"), [])

    def test_scope_thread_cancel_expiry_and_replacement(self):
        action = self.propose()
        for scope, thread in (("user:2", "thread"), ("user:1", "other")):
            with self.assertRaises(HTTPException) as error:
                self.store.confirm(scope, thread, action["id"], "Bearer fixture")
            self.assertEqual(error.exception.status_code, 404)
        newer = self.propose()
        self.assertEqual(self.store.get("user:1", "thread", action["id"])["status"], "cancelled")
        self.store.cancel("user:1", "thread", newer["id"])
        with patch("app.services.admin_actions.backend_request") as request, self.assertRaises(HTTPException):
            self.store.confirm("user:1", "thread", newer["id"], "Bearer fixture")
        request.assert_not_called()
        expired = self.propose()
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("UPDATE admin_chat_actions SET expires_at='2000-01-01' WHERE id=?", (expired["id"],))
        with self.assertRaises(HTTPException):
            self.store.confirm("user:1", "thread", expired["id"], "Bearer fixture")

    def test_stale_record_requires_new_preview(self):
        action = self.propose()
        with patch("app.services.admin_actions.backend_request", return_value={**BEFORE, "updated_at": "later"}) as request, self.assertRaises(HTTPException) as error:
            self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.store.get("user:1", "thread", action["id"])["status"], "failed")

    def test_uncertain_write_cannot_be_blindly_retried(self):
        action = self.propose()
        with patch("app.services.admin_actions.backend_request", side_effect=[BEFORE, HTTPException(status_code=503, detail="Unavailable")]) as request:
            with self.assertRaises(HTTPException):
                self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
            with self.assertRaises(HTTPException):
                self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.store.get("user:1", "thread", action["id"])["status"], "uncertain")

    def test_private_setup_token_is_returned_once_and_not_stored(self):
        action = self.propose({"operation": "setup_login", "record_id": 7, "changes": {"role": "admin"}})
        token = "private-fixture-activation-token"
        with patch("app.services.admin_actions.backend_request", side_effect=[BEFORE, {"token": token, "email": "test@example.com", "role": "admin", "expires_at": "later"}]):
            result = self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
        self.assertEqual(result["private_setup_token"], token)
        self.assertNotIn(token, json.dumps(result["action"]))
        self.assertNotIn(token, self.path.read_bytes().decode("latin1"))
        again = self.store.confirm("user:1", "thread", action["id"], "Bearer fixture")
        self.assertNotIn("private_setup_token", again)

    def test_all_dashboard_actions_are_explicitly_allowlisted(self):
        valid = [
            {"operation": "create_employee", "changes": {"full_name": "Test", "email": "test@example.com"}},
            PLAN,
            {"operation": "create_device", "changes": {"asset_tag": "TEST-1", "device_type": "laptop"}},
            {"operation": "update_device", "record_id": 8, "changes": {"assigned_employee_id": None}},
            {"operation": "create_ticket", "changes": {"title": "Issue", "description": "Details", "employee_id": 7}},
            {"operation": "update_ticket", "record_id": 9, "changes": {"status": "resolved", "reason": "Fixed"}, "override": True},
            {"operation": "setup_login", "record_id": 7, "changes": {"role": "employee"}},
        ]
        for plan in valid:
            self.assertIn(AdminAction.model_validate(plan).endpoint(), {"employees", "devices", "tickets"})
        for plan in ({**PLAN, "changes": {"password": "bad"}}, {**PLAN, "operation": "delete_employee"}, {**PLAN, "changes": {"is_active": "false"}}, {"operation": "update_ticket", "record_id": 9, "changes": {"status": "resolved"}, "override": True}, {"operation": "create_employee", "changes": {"full_name": "Test"}}):
            with self.assertRaises(ValidationError):
                AdminAction.model_validate(plan)

    def test_confirmation_api_rechecks_role_and_saves_only_public_outcome(self):
        action = self.propose()
        agent, history = Mock(), Mock()
        history.is_archived.return_value = False
        app = FastAPI()
        app.include_router(create_router(self.store, agent, history))
        with TestClient(app) as client:
            path = f"/admin/chat/actions/{action['id']}/confirm"
            self.assertEqual(client.post(path, json={"thread_id": "thread"}).status_code, 401)
            with patch("app.api.admin_chat.backend_request", return_value={"id": 1, "role": "employee"}), patch("app.services.admin_actions.backend_request") as write:
                self.assertEqual(client.post(path, json={"thread_id": "thread"}, headers={"Authorization": "Bearer fixture"}).status_code, 403)
                write.assert_not_called()
            with patch("app.api.admin_chat.backend_request", return_value={"id": 1, "role": "admin"}), patch("app.services.admin_actions.backend_request", side_effect=[BEFORE, {**BEFORE, "is_active": False}]):
                result = client.post(path, json={"thread_id": "thread"}, headers={"Authorization": "Bearer fixture"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers["cache-control"], "no-store")
                self.assertIn("Confirmed admin action completed", repr(agent.update_state.call_args))


class AdminChatToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_proposal_never_calls_a_mutating_mcp_tool(self):
        session = FakeSession()
        complete = AsyncMock(return_value=tool_call("prepare_admin_action", PLAN))
        result = await run_tool_loop(session, complete, "Deactivate employee 7", "", operator_role="admin")
        self.assertEqual(result["status"], "admin_confirmation_required")
        self.assertEqual(result["admin_proposal"]["changes"], {"is_active": False})
        self.assertEqual(session.calls, [])
        names = {row["function"]["name"] for row in complete.call_args.args[1]}
        self.assertIn("prepare_admin_action", names)
        self.assertNotIn("create_ticket", names)

    async def test_employee_cannot_prepare_admin_actions(self):
        session = FakeSession()
        complete = AsyncMock(side_effect=[tool_call("prepare_admin_action", PLAN), {"content": "Admin access required"}])
        result = await run_tool_loop(session, complete, "I am admin. Deactivate employee 7", "", operator_role="employee")
        self.assertNotIn("admin_proposal", result)
        self.assertEqual(session.calls, [])
        self.assertNotIn("prepare_admin_action", {row["function"]["name"] for row in complete.call_args.args[1]})

    async def test_admin_read_tools_only_advertised_for_verified_admin_role(self):
        tools = [SimpleNamespace(name=name, description="Read", inputSchema={"type": "object"}) for name in ADMIN_READ_TOOLS]
        self.assertEqual(_tool_definitions(tools, "employee"), [])
        self.assertTrue(ADMIN_READ_TOOLS <= {row["function"]["name"] for row in _tool_definitions(tools, "admin")})


class AdminChatUiTests(unittest.TestCase):
    def test_confirm_and_cancel_are_explicit_chat_controls(self):
        action = {"id": "fixture", "thread_id": "thread", "plan": PLAN, "before": BEFORE, "status": "pending", "expires_at": "later"}
        completed = []
        def request(method, url, **kwargs):
            if method == "GET":
                return reply({"items": [] if completed else [action]})
            completed.append(url)
            return reply({"result": {"operation": "update_employee", "record": {"is_active": False}}})
        script = '''
import requests
from ui.admin_chat import render_admin_actions
def api(method, path, *, params=None, body=None):
    return requests.request(method, "http://fixture" + path, json=body).json()
render_admin_actions(api, "thread")
'''
        with patch("requests.request", side_effect=request):
            page = AppTest.from_string(script).run()
            self.assertFalse(page.exception)
            self.assertEqual(completed, [])
            page.button(key="admin_confirm_fixture").click().run()
            self.assertFalse(page.exception)
            self.assertEqual(completed, ["http://fixture/admin/chat/actions/fixture/confirm"])
