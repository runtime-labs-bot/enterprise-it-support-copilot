# Enterprise IT Support Copilot

LangGraph IT support assistant with knowledge retrieval, web fallback, persistent
conversation memory, and live Meridian employee/device/ticket operations over MCP.

This repository contains the complete application. The Meridian backend in
`backend/` owns PostgreSQL data and ticket workflow rules. The AI agent and
Copilot API remain in `app/`, and Streamlit lives in `ui/`. Meridian runs on
port 8000, the Copilot API on 8001, and Streamlit on 8501 by default. The stdio
MCP process starts automatically on demand.

```text
app/           AI agent, Copilot API, and chat services
ui/            Employee chat and admin dashboard
backend/       Meridian API, MCP bridge, models, migrations, tests
scripts/       Setup and complete application verification
docker-compose.yml
```

Both Python services retain their own `app` package and virtual environment.
Start Meridian with `backend/` as its working directory; start Copilot from the
repository root. They communicate through REST/MCP rather than Python imports.
An additional `ai-agent/` directory is unnecessary for the existing structure.

## Local Windows setup

For the complete container stack, see [Docker Compose setup](docs/docker-compose.md): PostgreSQL, migrations, Meridian, Copilot API, Streamlit, and persistent chat storage.

```bat
cd /d C:\ITSupportCopilot
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Populate the provider credentials in `.env`; never commit the file. Configure
Meridian using [backend/README.md](backend/README.md) and run its migrations. The
backend environment belongs in `backend/.env`; Copilot settings belong in the
root `.env`. `MERIDIAN_BACKEND_DIR=backend` resolves from this repository root.
Then start the
Copilot API and UI in separate terminals:

```bat
python -m uvicorn app.api.main:app --reload --port 8001
```

```bat
python -m streamlit run ui\streamlit_app.py
```

See [integration and employee access instructions](docs/meridian-integration.md)
for all three application commands, one-time password setup, and the MCP tool list.

Employees authenticate using the chat email/password login form. They can
create their own tickets and close their own open/in-progress/resolved tickets
when the problem is fixed. Other status changes remain admin-only. The backend
enforces ownership and records status history. Credentials travel in HTTP headers
and run-scoped context, not chat text or checkpoint state.

## Verification

Use the [evaluation scorecard](docs/evaluations.md) for repeatable quality and
permission results, strict failure gates, and baseline comparisons:

```bat
python -m app.evaluation.scorecard --profile checks
python -m app.evaluation.scorecard --profile all --limit 5
```

```bat
python scripts\test_all.py
python -m pip check
python scripts\verify_meridian.py --live-model
```

The live check uses a temporary Meridian API on port 8766, actual Groq requests,
and generated database fixtures that are removed afterward. It includes Copilot
HTTP `/ask`, LangGraph, stdio MCP, REST, PostgreSQL, and employee closure history.
Unit tests also cover Streamlit credential forwarding and identity-scoped threads.

This is a local development system with linked users, JWT/refresh sessions, and
backend employee/admin access control. Production deployment hardening remains. Environment files,
credentials, virtual environments, and SQLite checkpoint data must stay out of Git.

Give employees a browser [password setup link](docs/password-setup.md) from the admin dashboard, then sign in normally. Access tokens refresh
automatically; logout and password reset revoke login sessions. No API-key copying
is required. Docker deployments now [restore login after browser refresh](docs/browser-login.md)
using an HttpOnly session cookie and encrypted server-side credentials.

Previous chats are restored after sign-in and can be reopened from the sidebar.
New chat starts a separate conversation. The login page has a Show password
option. Employees choose their passwords in the browser; terminal password tools remain available for trusted administrator recovery.

Conversation management includes search, rename, and archive/restore. Admin
accounts also have a dashboard for operational totals, ticket updates/history,
employee records, and device assignments. See the integration guide for admin
account setup and permissions. Dashboard actions use protected REST endpoints.

Admins can now perform those operations in [Admin chat](docs/admin-chat.md).
Read tools show searchable queues and summaries; mutations create a review card
and execute only after Confirm. Password setup links appear privately in the UI.

Employees can [edit their own ticket title/description before admin review](docs/ticket-review.md).
Opening a ticket as admin locks those details; further employee clarification
requires a new ticket. Self-service closure remains available after review.

Ticket creation supports [durable idempotency keys](docs/ticket-idempotency.md)
across API/MCP retries. The [evaluation guide](docs/evaluations.md) covers resumable
live batches and the offline GitHub Actions workflow.
