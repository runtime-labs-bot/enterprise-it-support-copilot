"""Verify the running Compose stack with temporary records and real stdio MCP.

Use --live-model to also check Groq, /ask, and saved history across login sessions.
Credentials go to the MCP subprocess through stdin, never CLI arguments or logs.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MCP_CHECK = '''
import asyncio, json, sys
from app.agent.meridian import connect_meridian
data = json.load(sys.stdin)
async def main():
    async with connect_meridian(data["credential"]) as session:
        result = await session.call_tool(data["tool"], data["arguments"])
        assert not result.isError, "MCP operation failed"
        output = result.structuredContent
        if output is None:
            output = json.loads("\\n".join(block.text for block in result.content if block.type == "text"))
        print(json.dumps(output))
asyncio.run(main())
'''


def checked(response, expected=200):
    if response.status_code != expected:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: expected {expected}, received {response.status_code}")
    return response.json() if expected != 204 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true")
    args = parser.parse_args()
    config = {**dotenv_values(ROOT / ".env.docker", interpolate=False), **os.environ}
    compose = ["docker", "compose", "--env-file", str(ROOT / ".env.docker")]
    employee_ids = []
    device_id = None
    with httpx.Client(base_url="http://127.0.0.1:" + config.get("MERIDIAN_PORT", "8000"), headers={"X-API-Key": config["DOCKER_ADMIN_API_KEY"]}, timeout=30, trust_env=False) as backend, httpx.Client(base_url="http://127.0.0.1:" + config.get("COPILOT_PORT", "8001"), timeout=90, trust_env=False) as copilot:
        checked(backend.get("/health/database"))
        checked(copilot.get("/"))
        with httpx.Client(trust_env=False) as ui:
            response = ui.get("http://127.0.0.1:" + config.get("STREAMLIT_PORT", "8501") + "/_stcore/health")
            assert response.status_code == 200
        try:
            accounts = {}
            for role in ("employee", "admin"):
                email = f"compose-{uuid4().hex}@example.com"
                employee = checked(backend.post("/employees", json={"full_name": "Compose Verification", "email": email}), 201)
                employee_ids.append(employee["id"])
                invite = checked(backend.post("/auth/setup-invitations", json={"employee_id": employee["id"], "role": role}), 201)
                password = secrets.token_urlsafe(24)
                setup = {"token": invite["token"], "password": password}
                assert checked(copilot.post("/auth/setup-password", json=setup))["role"] == role
                assert copilot.post("/auth/setup-password", json=setup).status_code == 400
                login = {"email": email, "password": password, "role": role}
                tokens = checked(copilot.post("/auth/login", json=login))
                accounts[role] = {"headers": {"Authorization": "Bearer " + tokens["access_token"]}, "tokens": tokens, "login": login, "id": employee["id"]}
            owner, admin = accounts["employee"], accounts["admin"]
            checked(copilot.get("/admin/summary", headers=admin["headers"]))
            assert copilot.get("/admin/summary", headers=owner["headers"]).status_code == 403
            device = checked(backend.post("/devices", json={"asset_tag": "VERIFY-" + uuid4().hex, "device_type": "laptop", "assigned_employee_id": owner["id"]}), 201)
            device_id = device["id"]

            def tool(name, arguments):
                payload = json.dumps({"credential": owner["tokens"]["access_token"], "tool": name, "arguments": arguments})
                result = subprocess.run(compose + ["exec", "-T", "copilot", "python", "-c", MCP_CHECK], input=payload, capture_output=True, text=True, cwd=ROOT, timeout=60)
                if result.returncode:
                    raise AssertionError("Container MCP check failed; inspect container logs")
                return json.loads(result.stdout)

            assert tool("get_current_employee", {})["employee_id"] == owner["id"]
            assert tool("get_device", {"device_id": device_id})["id"] == device_id
            ticket = tool("create_ticket", {"title": "Compose verification", "description": "Temporary integration fixture", "device_id": device_id})
            ticket_id = ticket["id"]
            assert ticket["employee_id"] == owner["id"]
            assert backend.patch(f"/tickets/{ticket_id}", json={"status": "resolved"}, headers={"X-API-Key": "", **owner["headers"]}).status_code == 403
            for status in ("in_progress", "resolved"):
                checked(copilot.patch(f"/admin/tickets/{ticket_id}", json={"status": status}, headers=admin["headers"]))
            assert tool("close_ticket", {"ticket_id": ticket_id})["status"] == "closed"
            history = checked(backend.get(f"/tickets/{ticket_id}/history"))
            assert history[-1]["actor_employee_id"] == owner["id"]
            assert history[-2]["actor_employee_id"] == admin["id"]
            print("PASS: container login/setup, permissions, device lookup, MCP creation, admin resolution, employee closure, and history")

            thread = "compose-" + uuid4().hex
            if args.live_model:
                answer = checked(copilot.post("/ask", json={"question": "Use get_current_employee to show my authenticated employee ID and work email.", "thread_id": thread}, headers=owner["headers"]))
                assert answer["status"] == "answered_meridian", "Live model did not complete the Meridian lookup"
                assert owner["login"]["email"] in answer["answer"], "Live answer did not include verified fixture identity"
                print("PASS: live model through container Copilot, LangGraph, MCP, REST, and PostgreSQL")
            checked(copilot.post("/auth/logout", json={"refresh_token": owner["tokens"]["refresh_token"]}), 204)
            assert copilot.get("/auth/me", headers=owner["headers"]).status_code == 401
            relogin = checked(copilot.post("/auth/login", json=owner["login"]))
            headers = {"Authorization": "Bearer " + relogin["access_token"]}
            if args.live_model:
                saved = checked(copilot.get("/conversations/" + thread, headers=headers))
                assert len(saved["messages"]) >= 2
                print("PASS: container chat history restored after logout and fresh login")
            print("PASS: container logout revokes access; fresh login succeeds")
        finally:
            for employee_id in employee_ids:
                for ticket in checked(backend.get("/tickets", params={"employee_id": employee_id, "limit": 100})):
                    checked(backend.delete(f"/tickets/{ticket['id']}"), 204)
            if device_id is not None:
                checked(backend.delete(f"/devices/{device_id}"), 204)
            for employee_id in employee_ids:
                checked(backend.delete(f"/employees/{employee_id}"), 204)
            print("Temporary container records cleaned up.")


if __name__ == "__main__":
    main()
