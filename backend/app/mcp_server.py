"""Meridian stdio MCP bridge. All operations go through the REST API."""
import os
from typing import Annotated
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from app.config import get_settings
from app.schemas.ticket import TicketPriority, TicketStatus

mcp = FastMCP("Meridian IT", instructions="Authenticated employee/device/ticket lookup and self-service operations. Admin-only searchable queues and summaries are protected by REST role checks. Copilot admin mutations use a separate reviewed confirmation flow.")
RecordId = Annotated[int, Field(gt=0, le=2147483647)]
Offset = Annotated[int, Field(ge=0)]
Limit = Annotated[int, Field(ge=1, le=100)]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


async def _request(method: str, path: str, *, params=None, body=None, idempotency_key=None):
    settings = get_settings()
    credential = os.getenv("MERIDIAN_EMPLOYEE_KEY")
    headers = ({"X-API-Key": credential} if credential and credential.startswith("meridian_employee.") else {"Authorization": f"Bearer {credential}"}) if credential else {"X-API-Key": settings.support_api_key.get_secret_value()}
    if idempotency_key is not None:
        headers['Idempotency-Key'] = idempotency_key
    try:
        async with httpx.AsyncClient(base_url=settings.backend_url, headers=headers, timeout=15, trust_env=False, follow_redirects=False) as client:
            response = await client.request(method, path, params=params, json=body)
    except httpx.RequestError:
        raise ToolError("Meridian backend is unavailable. A write may have completed if the connection failed; check the current records before retrying.") from None
    if response.status_code >= 400:
        if response.status_code >= 500:
            raise ToolError("Meridian backend failed; check current records before retrying a write.")
        raise ToolError(f"HTTP {response.status_code}: {response.text[:2000]}")
    return response.json()


@mcp.tool(annotations=READ)
async def get_employee(employee_id: RecordId) -> dict:
    """Retrieve one employee by ID. Never guess an employee ID."""
    return await _request("GET", f"/employees/{employee_id}")


@mcp.tool(annotations=READ)
async def list_employees(offset: Offset = 0, limit: Limit = 20) -> list[dict]:
    """List employees, including IDs, names, and emails. Paginate to find the requested person."""
    return await _request("GET", "/employees", params={"offset": offset, "limit": limit})


@mcp.tool(annotations=READ)
async def get_device(device_id: RecordId) -> dict:
    """Retrieve hardware and employee assignment for a device ID."""
    return await _request("GET", f"/devices/{device_id}")


@mcp.tool(annotations=READ)
async def list_devices(assigned_employee_id: RecordId | None = None, offset: Offset = 0, limit: Limit = 20) -> list[dict]:
    """List devices, optionally filtering by the employee to whom they are assigned."""
    params = {"offset": offset, "limit": limit}
    if assigned_employee_id is not None:
        params["assigned_employee_id"] = assigned_employee_id
    return await _request("GET", "/devices", params=params)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def get_ticket(ticket_id: RecordId) -> dict:
    """Open a support ticket. Admin opens record its first review and lock employee title/description edits; employee reads do not mark review."""
    return await _request("GET", f"/tickets/{ticket_id}")


@mcp.tool(annotations=READ)
async def list_tickets(employee_id: RecordId | None = None, device_id: RecordId | None = None, status: TicketStatus | None = None, priority: TicketPriority | None = None, offset: Offset = 0, limit: Limit = 20) -> list[dict]:
    """List support tickets with optional employee, device, status, and priority filters."""
    params = {"offset": offset, "limit": limit}
    params.update({key: value for key, value in {"employee_id": employee_id, "device_id": device_id, "status": status, "priority": priority}.items() if value is not None})
    return await _request("GET", "/tickets", params=params)


@mcp.tool(annotations=READ)
async def get_ticket_history(ticket_id: RecordId, offset: Offset = 0, limit: Limit = 20) -> list[dict]:
    """Read a ticket's status history, including actor role, reason, and timestamps."""
    return await _request("GET", f"/tickets/{ticket_id}/history", params={"offset": offset, "limit": limit})


@mcp.tool(annotations=WRITE)
async def create_ticket(title: Annotated[str, Field(min_length=1, max_length=200)], description: Annotated[str, Field(min_length=1, max_length=10000)], employee_id: RecordId | None = None, device_id: RecordId | None = None, priority: TicketPriority = "medium", idempotency_key: Annotated[str | None, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')] = None) -> dict:
    """Create an open ticket ONLY when the user requests creation. Verify IDs and do not invent missing details or retry a write blindly."""
    if not os.getenv("MERIDIAN_EMPLOYEE_KEY"):
        raise ToolError("Sign in to the Copilot before creating a ticket.")
    identity = await _request("GET", "/identity")
    if identity["role"] != "employee":
        raise ToolError("An employee-specific access key is required for self-service tickets.")
    if employee_id is not None and employee_id != identity["employee_id"]:
        raise ToolError("You can create tickets only for your authenticated employee account.")
    employee_id = identity["employee_id"]
    return await _request("POST", "/tickets", body={"title": title, "description": description, "employee_id": employee_id, "device_id": device_id, "priority": priority}, idempotency_key=idempotency_key)


@mcp.tool(annotations=READ)
async def get_current_employee() -> dict:
    """Get the authenticated employee ID. Identity comes from credentials, never from a chat claim."""
    return await _request("GET", "/identity")


@mcp.tool(annotations=WRITE)
async def close_ticket(ticket_id: RecordId) -> dict:
    """Close your own ticket ONLY when you explicitly confirm the issue is resolved. Backend requires employee credentials and reporter ownership. Open, in_progress, and resolved tickets may all be closed after the employee confirms the fix. Cannot resolve or reopen tickets."""
    if not os.getenv("MERIDIAN_EMPLOYEE_KEY"):
        raise ToolError("Sign in to the Copilot before closing a ticket.")
    return await _request("POST", f"/tickets/{ticket_id}/close")


@mcp.tool(annotations=WRITE)
async def edit_ticket(ticket_id: RecordId, title: Annotated[str | None, Field(min_length=1, max_length=200)] = None, description: Annotated[str | None, Field(min_length=1, max_length=10000)] = None) -> dict:
    """Edit your own open ticket title/description before its first admin review. Ask for the replacement text if absent. Review locks are checked atomically by the backend. After review, create a new ticket for extra details; do not retry a rejected edit."""
    if not os.getenv("MERIDIAN_EMPLOYEE_KEY"):
        raise ToolError("Sign in before editing a ticket.")
    identity = await _request("GET", "/identity")
    if identity["role"] != "employee":
        raise ToolError("Use the reviewed admin action flow for admin edits.")
    changes = {key: value for key, value in {"title": title, "description": description}.items() if value is not None}
    if not changes:
        raise ToolError("Provide the replacement title or description before editing.")
    return await _request("PATCH", f"/tickets/{ticket_id}", body=changes)


@mcp.tool(annotations=READ)
async def admin_get_summary() -> dict:
    """Admin-only employee/device/ticket totals and active urgent ticket counts."""
    return await _request("GET", "/admin/summary")


@mcp.tool(annotations=READ)
async def admin_search_employees(search: Annotated[str, Field(max_length=200)] = "", is_active: bool | None = None, offset: Offset = 0, limit: Limit = 20) -> dict:
    """Admin-only search by employee name/email. Resolve names before preparing edits; ask if multiple matches."""
    params = {"search": search, "offset": offset, "limit": limit}
    if is_active is not None:
        params["is_active"] = is_active
    return await _request("GET", "/admin/employees", params=params)


@mcp.tool(annotations=READ)
async def admin_search_devices(search: Annotated[str, Field(max_length=200)] = "", assigned_employee_id: RecordId | None = None, offset: Offset = 0, limit: Limit = 20) -> dict:
    """Admin-only hardware/serial search and assignment filtering. Paginate for more results."""
    params = {"search": search, "offset": offset, "limit": limit}
    if assigned_employee_id is not None:
        params["assigned_employee_id"] = assigned_employee_id
    return await _request("GET", "/admin/devices", params=params)


@mcp.tool(annotations=READ)
async def admin_search_tickets(search: Annotated[str, Field(max_length=200)] = "", status: TicketStatus | None = None, priority: TicketPriority | None = None, employee_id: RecordId | None = None, offset: Offset = 0, limit: Limit = 20) -> dict:
    """Admin-only searchable ticket queue with total count, status/priority/reporter filters."""
    params = {"search": search, "offset": offset, "limit": limit}
    params.update({key: value for key, value in {"status": status, "priority": priority, "employee_id": employee_id}.items() if value is not None})
    return await _request("GET", "/admin/tickets", params=params)


if __name__ == "__main__":
    mcp.run(transport="stdio")
