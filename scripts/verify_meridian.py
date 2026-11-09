"""Exercise real stdio MCP + REST + PostgreSQL, using temporary owned fixtures."""
import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values, load_dotenv

from app.agent.meridian import ALLOWED_TOOLS, ADMIN_READ_TOOLS, connect_meridian, meridian_installation, run_tool_loop


def decode(result):
    assert not result.isError, "MCP tool returned an error"
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads("\n".join(item.text for item in result.content if item.type == "text"))


async def verify_tools(employee_id, device_id, ticket_ids, employee_key, admin_client):
    async with connect_meridian(employee_key) as session:
        tools = (await session.list_tools()).tools
        assert {tool.name for tool in tools} == ALLOWED_TOOLS | ADMIN_READ_TOOLS
        assert (await session.call_tool("admin_get_summary", {})).isError
        assert decode(await session.call_tool("get_employee", {"employee_id": employee_id}))["id"] == employee_id
        assert decode(await session.call_tool("get_device", {"device_id": device_id}))["id"] == device_id
        for name, args in (("list_employees", {}), ("list_devices", {"assigned_employee_id": employee_id}), ("list_tickets", {"employee_id": employee_id})):
            assert not (await session.call_tool(name, args)).isError
        created = decode(await session.call_tool("create_ticket", {
            "title": "MCP integration fixture", "description": "Temporary verification ticket",
            "employee_id": employee_id, "device_id": device_id,
        }))
        ticket_id = created["id"]
        ticket_ids.append(ticket_id)
        assert created["status"] == "open"
        edited = decode(await session.call_tool("edit_ticket", {"ticket_id": ticket_id, "description": "Updated before review"}))
        assert edited["employee_can_edit"] and edited["description"] == "Updated before review"
        opened = admin_client.get(f"/tickets/{ticket_id}")
        assert opened.status_code == 200 and opened.json()["reviewed_at"] is not None
        assert (await session.call_tool("edit_ticket", {"ticket_id": ticket_id, "description": "Should be rejected"})).isError
        assert decode(await session.call_tool("get_current_employee", {}))["employee_id"] == employee_id
        self_fixed = decode(await session.call_tool("create_ticket", {
            "title": "Self-fixed fixture", "description": "Reporter fixed it before support responded",
            "employee_id": employee_id,
        }))
        ticket_ids.append(self_fixed["id"])
        assert decode(await session.call_tool("close_ticket", {"ticket_id": self_fixed["id"]}))["status"] == "closed"
        for state in ("in_progress", "resolved"):
            assert admin_client.patch(f"/tickets/{ticket_id}", json={"status": state}).status_code == 200
        assert decode(await session.call_tool("close_ticket", {"ticket_id": ticket_id}))["status"] == "closed"
        assert decode(await session.call_tool("get_ticket", {"ticket_id": ticket_id}))["status"] == "closed"
        assert (await session.call_tool("change_ticket_status", {"ticket_id": ticket_id, "status": "resolved"})).isError
        history = await session.call_tool("get_ticket_history", {"ticket_id": ticket_id})
        assert not history.isError
        records = decode(history)
        if isinstance(records, dict):
            records = records["result"]
        assert len(records) == 4
        assert records[-1]["actor_role"] == "employee"
        assert records[-1]["actor_employee_id"] == employee_id
        assert (await session.call_tool("get_employee", {"employee_id": -1})).isError
        assert (await session.call_tool("delete_ticket", {"ticket_id": ticket_id})).isError

        responses = iter([
            {"tool_calls": [{"id": "lookup", "type": "function", "function": {"name": "get_ticket", "arguments": json.dumps({"ticket_id": ticket_id})}}]},
            {"tool_calls": [{"id": "change", "type": "function", "function": {"name": "change_ticket_status", "arguments": json.dumps({"ticket_id": ticket_id, "status": "resolved"})}}]},
        ])
        async def complete(messages, definitions):
            return next(responses)
        result = await run_tool_loop(session, complete, f"Resolve ticket {ticket_id}", "")
        assert result["status"] == "meridian_forbidden"
        assert decode(await session.call_tool("get_ticket", {"ticket_id": ticket_id}))["status"] == "closed"
    print("PASS: authenticated creation, admin resolution, employee closure, and actor history through real MCP")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-model", action="store_true", help="Also invoke the configured-provider LangGraph with a read-only fixture query")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    backend, backend_python = meridian_installation()
    settings = dotenv_values(backend / ".env")
    # A separate temporary API port avoids interfering with the user's running API.
    base_url = "http://127.0.0.1:8766"
    os.environ["MERIDIAN_BACKEND_URL"] = base_url
    os.environ["MERIDIAN_MCP_ENABLED"] = "true"
    process = subprocess.Popen(
        [str(backend_python), "-B", "-m", "uvicorn", "app.main:app", "--port", "8766"],
        cwd=backend, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    employee_id = device_id = None
    extra_employee_ids = []
    ticket_ids = []
    try:
        with httpx.Client(base_url=base_url, headers={"X-API-Key": settings["ADMIN_API_KEY"]}, timeout=15, trust_env=False) as client:
            try:
                for _ in range(100):
                    assert process.poll() is None, "Temporary API failed to start"
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Temporary API startup timed out")
                token = uuid4().hex
                response = client.post("/employees", json={"full_name": "MCP Verification", "email": f"mcp-{token}@example.com"})
                response.raise_for_status()
                employee_id = response.json()["id"]
                password = secrets.token_urlsafe(24)
                response = client.post("/auth/users", json={"employee_id": employee_id, "password": password})
                response.raise_for_status()
                from fastapi.testclient import TestClient
                from app.api.main import app as api_app
                with TestClient(api_app) as api:
                    response = api.post("/auth/login", json={"email": f"mcp-{token}@example.com", "password": password})
                assert response.status_code == 200, "Password login through Copilot failed"
                login_tokens = response.json()
                employee_key = login_tokens["access_token"]
                response = client.post("/devices", json={"asset_tag": f"MCP-{token}", "device_type": "laptop", "assigned_employee_id": employee_id})
                response.raise_for_status()
                device_id = response.json()["id"]
                asyncio.run(verify_tools(employee_id, device_id, ticket_ids, employee_key, client))
                # Verify the dashboard proxy against real backend role checks and writes.
                admin_email = f"admin-{token}@example.com"
                admin_employee = client.post("/employees", json={"full_name": "Dashboard Integration Admin", "email": admin_email})
                admin_employee.raise_for_status()
                admin_id = admin_employee.json()["id"]
                extra_employee_ids.append(admin_id)
                created_user = client.post("/auth/users", json={"employee_id": admin_id, "password": password, "role": "admin"})
                created_user.raise_for_status()
                with TestClient(api_app) as api:
                    admin_login = api.post("/auth/login", json={"email": admin_email, "password": password})
                    assert admin_login.status_code == 200
                    admin_tokens = admin_login.json()
                    admin_headers = {"Authorization": "Bearer " + admin_tokens["access_token"]}
                    employee_headers = {"Authorization": "Bearer " + employee_key}
                    assert api.get("/admin/summary", headers=employee_headers).status_code == 403
                    summary = api.get("/admin/summary", headers=admin_headers)
                    assert summary.status_code == 200 and "tickets" in summary.json()
                    queue = api.get("/admin/tickets", params={"employee_id": employee_id, "limit": 1}, headers=admin_headers)
                    assert queue.status_code == 200 and queue.json()["total"] == 2
                    ticket_id = ticket_ids[0]
                    assert api.patch(f"/admin/tickets/{ticket_id}", json={"status": "open", "override": True, "reason": "Admin integration verification"}, headers=employee_headers).status_code == 403
                    changed = api.patch(f"/admin/tickets/{ticket_id}", json={"status": "open", "override": True, "reason": "Admin integration verification"}, headers=admin_headers)
                    assert changed.status_code == 200 and changed.json()["status"] == "open"
                    events = api.get(f"/admin/tickets/{ticket_id}/history", headers=admin_headers)
                    assert events.status_code == 200 and events.json()[-1]["actor_employee_id"] == admin_id
                    assigned = api.patch(f"/admin/devices/{device_id}", json={"assigned_employee_id": None}, headers=admin_headers)
                    assert assigned.status_code == 200 and assigned.json()["assigned_employee_id"] is None
                    assert api.patch(f"/admin/devices/{device_id}", json={"assigned_employee_id": employee_id}, headers=admin_headers).status_code == 200
                    new_employee = api.post("/admin/employees", json={"full_name": "Dashboard Created Fixture", "email": f"created-{token}@example.com"}, headers=admin_headers)
                    assert new_employee.status_code == 201
                    extra_employee_ids.append(new_employee.json()["id"])
                    from scripts.admin_chat_checks import verify_admin_chat
                    verify_admin_chat(api, client, admin_headers, employee_headers)
                    assert api.post("/auth/logout", json={"refresh_token": admin_tokens["refresh_token"]}).status_code == 204
                print("PASS: real admin dashboard API counts/queue/status history, ticket override, employee creation and device assignment; employee denied")
                if not args.live_model:
                    # Exercise the real API/auth/checkpoint path without depending
                    # on a provider's discretionary tool choice.
                    from unittest.mock import AsyncMock, patch
                    thread_id = f"history-verification-{token}"
                    with patch("app.agent.meridian._run", new=AsyncMock(return_value={"meridian_handled": True, "answer": "Saved history verification reply", "sources": [], "status": "answered_meridian", "meridian_tools": []})):
                        with TestClient(api_app) as api:
                            for question in ("History verification: first message", "History verification: follow-up"):
                                asked = api.post("/ask", json={"question": question, "thread_id": thread_id}, headers={"Authorization": "Bearer " + employee_key})
                                assert asked.status_code == 200
                if args.live_model:
                    from app.agent import meridian
                    runtime_context = meridian.MeridianContext(employee_api_key=employee_key)
                    original_run = meridian._run
                    async def diagnostic_run(*values):
                        try:
                            return await original_run(*values)
                        except Exception as error:
                            def describe(exc):
                                for child in getattr(exc, "exceptions", []):
                                    describe(child)
                                if not getattr(exc, "exceptions", None):
                                    body = getattr(exc, "body", {}) or {}
                                    detail = body.get("error", {}).get("message", "") if isinstance(body, dict) else ""
                                    print(f"Live-model diagnostic: {type(exc).__name__}, status={getattr(exc, 'status_code', None)}, {detail[:500]}")
                            describe(error)
                            raise
                    meridian._run = diagnostic_run
                    from langchain_core.messages import HumanMessage
                    from app.agent.graph import app
                    from fastapi.testclient import TestClient
                    from app.api.main import app as api_app

                    def ask_api(question, thread_id):
                        with TestClient(api_app) as api:
                            response = api.post("/ask", json={"question": question, "thread_id": thread_id}, headers={"Authorization": "Bearer " + employee_key})
                        assert response.status_code == 200, "Copilot /ask failed"
                        result = response.json()
                        assert result["thread_id"] == thread_id
                        return result
                    question = f"Show the employee record for employee ID {employee_id} and list their assigned devices. Do not change anything."
                    result = app.invoke({"question": question, "messages": [HumanMessage(content=question)]}, config={"configurable": {"thread_id": f"mcp-verification-{token}"}}, context=runtime_context)
                    assert result["status"] == "answered_meridian", result["status"]
                    assert {"get_employee", "list_employees"} & set(result.get("meridian_tools", [])), "Live model did not retrieve employee information"
                    assert "list_devices" in result.get("meridian_tools", []), "Live model did not retrieve devices"
                    assert not ({"create_ticket", "change_ticket_status"} & set(result["meridian_tools"]))
                    print("PASS: configured LLM -> existing LangGraph -> MCP -> REST -> PostgreSQL read flow")
                    # Leave room in the local account's model token/minute quota.
                    time.sleep(15)
                    thread_id = f"mcp-live-writes-{token}"
                    question = f"Create exactly one IT support ticket for employee ID {employee_id}, device ID {device_id}. Use title Live MCP fixture and description Intermittent Wi-Fi during verification. Use medium priority."
                    result = ask_api(question, thread_id)
                    # Discover owned fixtures before assertions, so cleanup also runs if the model failed after writing.
                    rows = client.get("/tickets", params={"employee_id": employee_id, "limit": 100}).json()
                    new_ids = [row["id"] for row in rows if row["id"] not in ticket_ids]
                    ticket_ids.extend(new_ids)
                    assert result["status"] == "answered_meridian", result["status"]
                    assert len(new_ids) == 1, "Live create did not produce exactly one ticket: " + result["answer"]
                    live_id = new_ids[0]
                    assert client.get(f"/tickets/{live_id}").json()["status"] == "open"
                    support_headers = {"X-API-Key": settings["SUPPORT_API_KEY"]}
                    assert client.patch(f"/tickets/{live_id}", json={"status": "in_progress"}, headers=support_headers).status_code == 403
                    assert len(client.get(f"/tickets/{live_id}/history").json()) == 1
                    with TestClient(api_app) as api:
                        refreshed = api.post("/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]})
                    assert refreshed.status_code == 200, "Refresh through Copilot failed"
                    login_tokens = refreshed.json()
                    employee_key = login_tokens["access_token"]
                    time.sleep(15)
                    question = "I fixed the problem myself before support responded. Close the ticket you just created for me."
                    result = ask_api(question, thread_id)
                    assert result["status"] == "answered_meridian", result["status"]
                    assert client.get(f"/tickets/{live_id}").json()["status"] == "closed"
                    assert client.get(f"/tickets/{live_id}/history").json()[-1]["actor_employee_id"] == employee_id
                    history = client.get(f"/tickets/{live_id}/history").json()
                    assert len(history) == 2
                    assert history[-1]["old_status"] == "open"
                    assert employee_key.encode() not in (ROOT / "data/checkpoints/checkpoints.sqlite").read_bytes()
                    assert password.encode() not in (ROOT / "data/checkpoints/checkpoints.sqlite").read_bytes()
                    assert login_tokens["refresh_token"].encode() not in (ROOT / "data/checkpoints/checkpoints.sqlite").read_bytes()
                    print("PASS: password login -> Copilot /ask -> live model -> MCP -> PostgreSQL; refresh preserves conversation; owner closure audited; credentials absent from checkpoints")
                with TestClient(api_app) as api:
                    assert api.post("/auth/logout", json={"refresh_token": login_tokens["refresh_token"]}).status_code == 204
                    assert api.post("/ask", json={"question": "Show my tickets"}, headers={"Authorization": "Bearer " + employee_key}).status_code == 401
                    assert api.post("/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]}).status_code == 401
                print("PASS: logout revokes both access and refresh through Copilot before any model/tool call")
                with TestClient(api_app) as api:
                    logged_in_again = api.post("/auth/login", json={"email": f"mcp-{token}@example.com", "password": password})
                    assert logged_in_again.status_code == 200
                    again = logged_in_again.json()
                    headers = {"Authorization": "Bearer " + again["access_token"]}
                    index = api.get("/conversations", headers=headers)
                    assert index.status_code == 200
                    assert thread_id in {item["thread_id"] for item in index.json()["items"]}
                    saved = api.get(f"/conversations/{thread_id}", headers=headers)
                    assert saved.status_code == 200
                    assert len(saved.json()["messages"]) == 4
                    assert saved.json()["messages"][0]["role"] == "user"
                    if args.live_model:
                        assert "Close" in saved.json()["messages"][2]["content"]
                    else:
                        assert saved.json()["messages"][2]["content"] == "History verification: follow-up"
                    renamed = api.patch(f"/conversations/{thread_id}", json={"title": "Verified saved chat"}, headers=headers)
                    assert renamed.status_code == 200
                    assert renamed.json()["messages"] == saved.json()["messages"]
                    assert api.get("/conversations", params={"query": "Verified saved chat"}, headers=headers).json()["items"][0]["thread_id"] == thread_id
                    assert api.patch(f"/conversations/{thread_id}", json={"archived": True}, headers=headers).status_code == 200
                    assert thread_id not in {item["thread_id"] for item in api.get("/conversations", headers=headers).json()["items"]}
                    assert api.get("/conversations", params={"archived": True}, headers=headers).json()["items"][0]["thread_id"] == thread_id
                    assert api.post("/ask", json={"question": "Must restore first", "thread_id": thread_id}, headers=headers).status_code == 409
                    restored = api.patch(f"/conversations/{thread_id}", json={"archived": False}, headers=headers)
                    assert restored.status_code == 200 and restored.json()["messages"] == saved.json()["messages"]
                    assert api.post("/auth/logout", json={"refresh_token": again["refresh_token"]}).status_code == 204
                print("PASS: real API/auth/checkpoint history restores after logout and fresh login" + ("" if args.live_model else " (model boundary stubbed)"))
                print("PASS: real conversation rename/search/archive/restore preserves the transcript")
            finally:
                # Fixtures are isolated by their generated employee, including any uncertain model write.
                if employee_id is not None:
                    response = client.get("/tickets", params={"employee_id": employee_id, "limit": 100})
                    if response.status_code == 200:
                        ticket_ids[:] = list({*ticket_ids, *(row["id"] for row in response.json())})
                for ticket_id in ticket_ids:
                    response = client.delete(f"/tickets/{ticket_id}")
                    assert response.status_code == 204, "Ticket fixture cleanup failed"
                if device_id is not None:
                    assert client.delete(f"/devices/{device_id}").status_code == 204, "Device fixture cleanup failed"
                if employee_id is not None:
                    assert client.delete(f"/employees/{employee_id}").status_code == 204, "Employee fixture cleanup failed"
                for extra_id in extra_employee_ids:
                    assert client.delete(f"/employees/{extra_id}").status_code == 204, "Admin/employee fixture cleanup failed"
                print("Fixture cleanup completed.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
