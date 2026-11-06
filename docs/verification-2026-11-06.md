# Integration verification — 2026-11-06

Verified locally on Windows with PostgreSQL 18 and the two independent virtual
environments. This report covers the current employee self-service policy.

| Check | Result |
| --- | --- |
| Meridian PostgreSQL integration suite | 30 tests passed |
| Copilot tool-loop, routing, runtime credential, API, and Streamlit tests | 18 tests passed |
| Dependency consistency, both environments (`pip check`) | Passed |
| Alembic model/schema consistency | Passed; head `0005_employee_closure` |
| Actual stdio MCP tool discovery and calls | Passed |
| Live Groq/LangGraph employee and device retrieval | Passed |
| Copilot HTTP `/ask` to live model/MCP/REST/PostgreSQL ticket creation | Passed |
| Conversational closure of the caller's own open ticket | Passed |
| Creation, admin resolution, and employee closure through MCP | Passed |
| Reject another employee's closure and service-key status updates | Passed |
| Audit event contains actual prior status and authenticated employee ID | Passed |
| Runtime credentials excluded from checkpoint state | Passed |
| Generated integration records cleaned up | Passed |
| Staged configured-secret/credential/private-artifact scan | Passed |

The Streamlit AppTest exercises the password sidebar, header forwarding, thread
ID, and conversation reset on credential changes with the HTTP request mocked.
The separate live integration test exercises the actual Copilot FastAPI `/ask`
route, configured Groq account, LangGraph, spawned stdio MCP server, temporary
Meridian HTTP API, and PostgreSQL. No production ticket is modified by the check;
generated employee/device/ticket fixtures are removed. Database ID sequences may
advance during testing. Test checkpoints remain local and ignored by Git.

The live model may choose either the individual employee lookup or paginated
employee listing. The verification accepts both legitimate retrieval paths and
checks ticket creation/closure against actual database-backed REST responses.

## Changes made during verification

- Excluded the complete checkpoint directory, including WAL/SHM sidecars, from Git.
- Added API and Streamlit credential-handoff/identity-isolation regression tests.
- Extended the live verification script to cover HTTP `/ask`, rather than only
  invoking the graph directly.
- Made fresh Meridian database setup generate the required support/admin keys.
- Added a credential-free Copilot environment example and consolidated setup docs.

## Remaining development limitations

The older Meridian read and employee/device CRUD endpoints retain their existing
local development access behavior. Full authentication/authorization across those
APIs is not complete. Employee keys are seven-day signed bearer credentials, with
no individual revocation, password login, or account recovery. The existing Groq,
Pinecone, and Tavily provider configuration is required for their corresponding
features. The web/knowledge paths were not sent new external provider requests
during this verification; routing back to the existing knowledge flow is covered
by tests. Production deployment hardening and a fresh-machine install were not
part of this local integration check.

## Repeat the checks

```bat
cd /d C:\ITSupportCopilot\backend
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m alembic check
.venv\Scripts\python -m pip check
```

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m pip check
.venv\Scripts\python scripts\verify_meridian.py --live-model
```
