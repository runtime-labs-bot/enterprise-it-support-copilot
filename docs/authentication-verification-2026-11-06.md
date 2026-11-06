# Password login verification — 2026-11-06

The manual employee-key UI has been replaced by email/password login. This
verification supersedes the authentication limitations in the earlier integration
snapshot while preserving the employee-owned creation/closure workflow.

| Check | Result |
| --- | --- |
| Meridian PostgreSQL suite, including authentication/access control | 41 tests passed |
| Copilot tool-loop, API, runtime and Streamlit suite | 24 tests passed |
| Alembic consistency | Passed; `0006_users_and_sessions` |
| Dependency consistency in both environments | Passed |
| Live password login through the Copilot HTTP API | Passed |
| JWT identity through LangGraph/MCP/REST/PostgreSQL | Passed |
| Employee creates and closes their own open ticket | Passed |
| Refresh rotation preserves the conversation across access-token changes | Passed |
| Logout rejects access and refresh before further model/tool execution | Passed |
| Password, access JWT and refresh credential absent from checkpoints | Passed |
| Temporary integration users, sessions and records cleaned up | Passed |

The database tests cover Argon2id password hashes, duplicate account prevention,
JWT signature/algorithm/issuer/audience/expiry checks, wrong token use, refresh
rotation and replay-family revocation, logout, password reset revocation, inactive
accounts/employees, basic login lockout, employee ticket/history ownership,
admin status updates, directory/device access control, and retirement of old
employee keys after password-account provisioning.

Streamlit AppTest covers the normal email/password form, failed login, token
refresh without re-entering credentials, revoked refresh, logout and chat reset.
Its HTTP boundary is mocked; the independent live check uses actual Copilot
FastAPI routes, Groq, LangGraph, spawned stdio MCP, Meridian REST and PostgreSQL.
No real employee password is set or changed by tests/migrations.

The initial real password must be set once through the local hidden prompt:

```bat
cd /d C:\MeridianITBackend
.venv\Scripts\python scripts\set_user_password.py --email rd@example.com --role employee
```

Then restart the services and sign in at http://localhost:8501. Use the intended
employee's existing email. The administrator can provision/reset accounts; there
is no public account-claiming or admin self-registration endpoint.

The active Streamlit tab stays signed in while its server session exists. Browser
refresh/reopening can require login again; persistent browser remember-me cookies
and SSO/MFA are not implemented. Production still requires HTTPS, managed secrets,
broader request-rate controls, monitoring, and account recovery.
