# Meridian Copilot integration

Meridian and the Copilot have separate environments and databases. The Copilot
launches a stdio MCP subprocess from Meridian, which calls the Meridian REST API.

## Current ticket permissions

| Action | Employee | Admin |
| --- | --- | --- |
| Create ticket | Own authenticated employee account | Allowed |
| Mark in_progress or resolved | No | Allowed |
| Close resolved ticket | Own ticket only | Allowed |
| Close open/in_progress ticket after fixing it | Own ticket only | Override with reason |
| Reopen, reassign reporter, change existing priority, delete | No | Allowed |

Employees can close their own ticket after fixing the issue, whether its status
is open, in_progress, or resolved. They do not need to wait for support. The backend checks identity, ownership, and current status. Closure
adds actor_role=employee and actor_employee_id to status history. Repeated closure
by the owner is a no-op. Previous history is retained with its original actors.

## Start the applications (separate CMD terminals)

```bat
cd /d C:\MeridianITBackend
.venv\Scripts\activate
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\activate
python -m uvicorn app.api.main:app --reload --port 8001
```

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\activate
python -m streamlit run ui\streamlit_app.py
```

MCP starts automatically on demand; no fourth terminal is required.

## Set up an employee credential

1. Open Meridian Swagger at http://127.0.0.1:8000/docs.
2. Authorize with ADMIN_API_KEY from Meridian's local .env.
3. Execute POST /employees/{employee_id}/access-key for the intended employee.
4. Give the returned api_key privately to that employee.
5. Enter it in the chat sidebar's Employee access key field.

The key is signed, expires after seven days, and is bound to an active employee.
Deactivating the employee disables their credentials. Rotating ADMIN_API_KEY
invalidates all employee keys. Individual token revocation/password login/account
recovery are not implemented. Never put credentials in chat messages.

Try: "Create a ticket for my laptop: Wi-Fi drops every ten minutes."
If you fixed the problem yourself, ask: "The issue is fixed. Close ticket 29."
Use the actual ID returned at creation. The Copilot refreshes live status rather
than relying on earlier conversation. Missing credentials prevent self-service
writes; pretending to be an admin in chat grants no privileges.

## API and tools

- POST /tickets: employee credential can create only for its own employee_id.
- POST /tickets/{id}/close: reporting employee only, from open, in_progress, or
  resolved; another employee or service role is rejected (403).
- PATCH /tickets/{id}: admin status changes; employee may submit only status=closed
  and gets the same ownership/state checks as the dedicated close endpoint.
- PATCH /tickets/{id}/admin: admin overrides require a reason for status changes.
- GET /tickets/{id}/history: paginated status history.
- GET /identity: role and employee ID from the request credential.

Ten MCP tools: get_employee, list_employees, get_device, list_devices, get_ticket,
list_tickets, get_ticket_history, get_current_employee, create_ticket, close_ticket.
There is no generic status-change, delete, SQL, or arbitrary HTTP tool.

The chat sends X-Meridian-Employee-Key to /ask. It travels through ephemeral
LangGraph runtime context and the MCP subprocess environment, never through
model arguments, conversation messages, or checkpoint state. Conversations are
scoped by credential, and changing the sidebar key starts a fresh conversation.
The older read/employee/device APIs still use their development access behavior;
full account login and authorization across those APIs are separate work.

The support service key remains usable for legacy reads/internal ticket creation
but cannot close tickets. Employee-facing MCP creation/closure requires an
employee-specific credential, never the shared support or admin key.

## Configuration

Copilot .env additions (already configured locally):

```dotenv
MERIDIAN_MCP_ENABLED=true
MERIDIAN_BACKEND_DIR=C:/MeridianITBackend
MERIDIAN_BACKEND_URL=http://127.0.0.1:8000
API_URL=http://127.0.0.1:8001/ask
```

Optional MERIDIAN_MCP_PYTHON overrides the backend Python executable. Windows
paths are local defaults; configure paths/networking for Linux or containers.
Set MERIDIAN_MCP_ENABLED=false to use the original knowledge/web workflow only.

The tool loop is bounded. Failed writes are not retried, and confirmed writes
remain visible if the model summary fails. Inspect tickets/history after a write
timeout before repeating it. General technical and policy questions retain the
original knowledge/web workflow.

## Verification

```bat
cd /d C:\MeridianITBackend
.venv\Scripts\python -m unittest discover -s tests -v
```

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python -m unittest discover -s tests -p "test_meridian*.py" -v
.venv\Scripts\python scripts\verify_meridian.py --live-model
```

The integration check starts a temporary API on port 8766, creates generated
fixtures, verifies both admin-resolved closure and direct employee closure, and removes the
fixtures afterward. --live-model uses the configured Groq account and includes
short pauses for its token limit. Omit it for deterministic protocol checks.
Tests can advance database ID sequences.

SDK references: https://py.sdk.modelcontextprotocol.io/v1/ and
https://console.groq.com/docs/tool-use/overview. Both projects pin mcp>=1.28,<2.