# Enterprise IT Support Copilot

LangGraph IT support assistant with knowledge retrieval, web fallback, persistent
conversation memory, and live Meridian employee/device/ticket operations over MCP.

The independent [Meridian backend](https://github.com/rushberry02/meridian-it-backend)
owns PostgreSQL data and ticket workflow rules. This repository hosts the Copilot
API and Streamlit chat. Meridian runs on port 8000, the Copilot API on 8001, and
Streamlit on 8501. The stdio MCP process starts automatically on demand.

## Local Windows setup

```bat
cd /d C:\ITSupportCopilot
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Populate the provider credentials in `.env`; never commit the file. Configure
Meridian separately using its README and run its migrations. Then start the
Copilot API and UI in separate terminals:

```bat
python -m uvicorn app.api.main:app --reload --port 8001
```

```bat
python -m streamlit run ui\streamlit_app.py
```

See [integration and employee access instructions](docs/meridian-integration.md)
for all three application commands, credential issuance, and the MCP tool list.

Employees authenticate using the chat sidebar's access-key field. They can
create their own tickets and close their own open/in-progress/resolved tickets
when the problem is fixed. Other status changes remain admin-only. The backend
enforces ownership and records status history. Credentials travel in HTTP headers
and run-scoped context, not chat text or checkpoint state.

## Verification

```bat
python -m unittest discover -s tests -v
python -m pip check
python scripts\verify_meridian.py --live-model
```

The live check uses a temporary Meridian API on port 8766, actual Groq requests,
and generated database fixtures that are removed afterward. It includes Copilot
HTTP `/ask`, LangGraph, stdio MCP, REST, PostgreSQL, and employee closure history.
Unit tests also cover Streamlit credential forwarding and identity-scoped threads.

This is a local development system. Full user login and authorization for the
older Meridian employee/device/read APIs remain unfinished. Environment files,
credentials, virtual environments, and SQLite checkpoint data must stay out of Git.
