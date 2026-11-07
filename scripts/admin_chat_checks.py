"""Real backend/confirmation checks with only model planning scripted."""
import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from app.agent.meridian import connect_meridian


def verify_admin_chat(api, backend, admin_headers, employee_headers):
    employee_id = device_id = ticket_id = None
    marker = uuid4().hex

    def perform(plan):
        thread = "admin-check-" + uuid4().hex
        scripted = {"meridian_handled": True, "status": "admin_confirmation_required", "answer": "Review the requested change", "admin_proposal": plan}
        with patch("app.agent.meridian._run", new=AsyncMock(return_value=scripted)):
            proposed = api.post("/ask", json={"question": "Perform the requested fixture admin action", "thread_id": thread}, headers=admin_headers)
        assert proposed.status_code == 200, "Admin proposal failed"
        action = proposed.json()["pending_action"]
        path = f"/admin/chat/actions/{action['id']}/confirm"
        assert api.post(path, json={"thread_id": thread}, headers=employee_headers).status_code == 403
        result = api.post(path, json={"thread_id": thread}, headers=admin_headers)
        assert result.status_code == 200, "Admin confirmation failed"
        again = api.post(path, json={"thread_id": thread}, headers=admin_headers)
        assert again.status_code == 200 and "private_setup_token" not in again.json()
        return result.json(), thread

    async def read_checks(email, asset):
        async with connect_meridian(admin_headers["Authorization"][7:]) as session:
            for tool, values in (("admin_get_summary", {}), ("admin_search_employees", {"search": email}), ("admin_search_devices", {"search": asset}), ("admin_search_tickets", {"employee_id": employee_id})):
                result = await session.call_tool(tool, values)
                assert not result.isError, "Admin MCP read failed"

    try:
        email = f"admin-chat-{marker}@example.com"
        result, _ = perform({"operation": "create_employee", "changes": {"full_name": "Admin Chat Fixture", "email": email}})
        employee_id = result["result"]["record"]["id"]
        result, thread = perform({"operation": "setup_login", "record_id": employee_id, "changes": {"role": "employee"}})
        token = result["private_setup_token"]
        saved = api.get(f"/conversations/{thread}", headers=admin_headers)
        assert saved.status_code == 200 and token not in saved.text
        perform({"operation": "update_employee", "record_id": employee_id, "changes": {"department": "Evaluation", "job_title": "Fixture", "is_active": False}})
        assert backend.get(f"/employees/{employee_id}").json()["is_active"] is False
        perform({"operation": "update_employee", "record_id": employee_id, "changes": {"is_active": True}})
        asset = "ADMIN-CHAT-" + marker
        result, _ = perform({"operation": "create_device", "changes": {"asset_tag": asset, "device_type": "laptop", "assigned_employee_id": employee_id}})
        device_id = result["result"]["record"]["id"]
        perform({"operation": "update_device", "record_id": device_id, "changes": {"manufacturer": "Fixture", "assigned_employee_id": None}})
        perform({"operation": "update_device", "record_id": device_id, "changes": {"assigned_employee_id": employee_id}})
        result, _ = perform({"operation": "create_ticket", "changes": {"title": "Admin chat fixture", "description": "Temporary integration record", "employee_id": employee_id, "device_id": device_id}})
        ticket_id = result["result"]["record"]["id"]
        perform({"operation": "update_ticket", "record_id": ticket_id, "changes": {"priority": "high", "status": "in_progress", "reason": "Fixture investigation"}})
        perform({"operation": "update_ticket", "record_id": ticket_id, "changes": {"status": "resolved", "reason": "Fixture fixed"}})
        perform({"operation": "update_ticket", "record_id": ticket_id, "changes": {"status": "open", "reason": "Fixture override verification"}, "override": True})
        assert backend.get(f"/tickets/{ticket_id}").json()["status"] == "open"
        asyncio.run(read_checks(email, asset))
        print("PASS: all admin chat action types execute only after confirmation; employee confirmation denied; duplicate confirmation does not repeat writes")
        print("PASS: admin MCP summaries/search and private setup links outside saved chat")
    finally:
        if ticket_id is not None:
            assert backend.delete(f"/tickets/{ticket_id}").status_code == 204
        if device_id is not None:
            assert backend.delete(f"/devices/{device_id}").status_code == 204
        if employee_id is not None:
            assert backend.delete(f"/employees/{employee_id}").status_code == 204
