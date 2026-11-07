# Employee login and Meridian integration

Employees open the Copilot, enter their work email and password, and start
chatting. The UI no longer displays API-key fields. Admins provision a linked
login account once; employee identity comes from verified authentication.

## One-time account setup

An administrator creates or selects the employee in **Admin dashboard → Employees**,
opens **Set up login account**, chooses the approved company role, and generates
a private setup link. The employee chooses and confirms a 12-128 character
password in the browser, with an optional **Show password** control. Links expire
after 24 hours and work once. See [password setup](password-setup.md).

For the first Docker administrator, use the trusted activation-link command in
the [Compose instructions](docker-compose.md). Backend terminal password tools
remain available for administrator recovery. No real employee password is
assigned by code or migrations, and passwords are never command-line arguments.

Admins may also use POST /auth/users or PUT /auth/users/{employee_id}/password
on Meridian with admin authentication. There is no public registration endpoint
that lets a person claim someone else's employee record or an admin role.

## Start the applications (separate CMD terminals)

```bat
cd /d C:\ITSupportCopilot\backend
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

Open http://localhost:8501 and sign in. The stdio MCP subprocess starts on demand.
An existing installation already has migration 0007_password_invitations applied.
Fresh installations must install the backend requirements before migrations.

## Login and session behavior

- The users table links one-to-one to employees; names/email stay on employees.
- Passwords use Argon2id hashes. Tokens/passwords never reach the model or its
  conversation/checkpoint state.
- Login returns a 15-minute JWT access token and a seven-day refresh session.
- JWT signature, expiry, issuer/audience, and database session/user/employee state
  are checked. The database role determines privileges.
- Streamlit keeps tokens in server-side session state and refreshes access tokens
  automatically. No manual credential copying is required.
- Refresh tokens rotate atomically; only hashes are stored. Replaying a used
  refresh token revokes that session family, including its access JWTs.
- Sign out revokes the server session and clears the UI conversation.
- Password resets revoke all sessions for that login. Disabled users/employees
  and expired/revoked sessions are rejected.
- Five incorrect password attempts lock the account for fifteen minutes. Errors
  do not reveal whether the email has a login account.

The active Streamlit tab retains its login across chat interactions. Refreshing
or reopening the browser tab can require another ordinary login; persistent
browser remember-me cookies are not implemented. If a logout request cannot
reach the server, the UI clears local state and reports that server revocation
could not be confirmed.

## API

Both APIs expose POST /auth/login, /auth/refresh, /auth/logout and GET /auth/me.
Copilot forwards these requests to Meridian. API clients use Authorization:
Bearer <access JWT> for /ask and protected backend operations. The browser chat
handles all of this automatically. Copilot verifies identity before running the
agent, scopes conversation checkpoints by authenticated user ID, and passes the
JWT only through ephemeral runtime context and the MCP subprocess environment.
MCP sends it as a Bearer header, never as a model-supplied tool argument.

Legacy employee keys work only for employees without a password account. Once
an account exists, old employee keys and further key issuance are rejected.
Internal support/admin service keys remain for provisioning/internal operations;
normal employees never see them. Do not share secrets in chat or commit .env.

## Access control

| Operation | Employee | Admin |
| --- | --- | --- |
| Read employee profile | Self only | All |
| Read devices | Assigned devices only | All |
| Read/list tickets and history | Own tickets only | All |
| Create ticket | Own employee account | Allowed |
| Edit ticket title/description | Own open ticket before first admin review | Allowed |
| Close open/in_progress/resolved ticket after fixing it | Own ticket only | Allowed |
| Resolve/reopen/reassign/delete or change existing priority | No | Allowed |
| Create/edit/delete employees or devices | No | Allowed |

Another employee's individual record/history returns 404 without disclosing it.
Explicitly requesting another employee's list returns 403. Unauthenticated reads
are rejected. Ownership is enforced at the backend independently of model prompts.
Admins may use a login JWT as the HTTP Bearer credential in Meridian Swagger;
normal status changes use PATCH /tickets/{id}, overrides via /admin need a reason.
Admin chat prepares dashboard mutations for explicit confirmation; see
[Admin chat](admin-chat.md). Employee chat has a separate restricted tool set.

The employee MCP tools are get_employee, list_employees, get_device,
list_devices, get_ticket, list_tickets, get_ticket_history, get_current_employee,
create_ticket, edit_ticket, and close_ticket. Opening an individual ticket as
admin records first review and locks employee detail edits; queue listings do not.
See [review rules](ticket-review.md). History records actual status transitions and
the employee who closed a ticket. Duplicate closure by the owner is a no-op.

## Configuration and tests

Copilot .env keeps its existing provider credentials and these settings:

```dotenv
MERIDIAN_MCP_ENABLED=true
MERIDIAN_BACKEND_DIR=C:/MeridianITBackend
MERIDIAN_BACKEND_URL=http://127.0.0.1:8000
API_URL=http://127.0.0.1:8001/ask
```

Meridian owns AUTH_JWT_SECRET in its ignored .env, plus ACCESS_TOKEN_MINUTES=15
and REFRESH_SESSION_DAYS=7. Setup generates the signing secret automatically.
Do not copy that secret into the Copilot or expose it in the UI. For Linux or
containers, configure paths/networking appropriately; defaults target Windows.

```bat
cd /d C:\ITSupportCopilot\backend
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m alembic check
```

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python scripts\verify_meridian.py --live-model
```

The live check creates temporary accounts and records, verifies password login,
refresh continuity, live Groq/MCP ticket operations and logout rejection, then
removes fixtures. Tests can advance database ID sequences. The UI tests exercise
normal login, failure messages, automatic refresh, expiry, and sign-out.

This is still a local development deployment. Production requires HTTPS,
managed secrets, broader request-rate controls, operational monitoring, and an
account recovery process. SSO/MFA and persistent remember-me cookies are not added.

References: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ and
https://frankie567.github.io/pwdlib/guide/
## Saved conversations and password visibility

After signing in, the UI restores the latest account-linked chat. Previous chats
in the sidebar lets you reopen earlier conversations; New chat starts a separate
thread. Load older chats retrieves subsequent pages. History is read from the
existing persistent SQLite checkpoints and is scoped to the verified user ID.
Signing out clears browser session state but preserves saved conversations.
Authenticated GET /conversations and GET /conversations/{thread_id} serve the
index and messages; another account cannot list or read them. Earlier anonymous
or credential-hash-only threads are not assigned to a user automatically.

The login page has a Show password checkbox. For the local password setup CLI,
add --show-password to display both entries in your terminal. It still defaults
to masked input. Visibility changes do not write passwords to history or logs.

## Conversation management

Search chats matches conversation names. Open Manage conversation to rename the
current chat or archive it. Show archived chats finds archived conversations;
Restore chat preserves all messages and allows the conversation to continue.
Archived conversations reject new messages until restored. These settings live
in a separate SQLite metadata table and never rewrite the LangGraph transcript.
All list/read/rename/archive endpoints remain scoped to the authenticated user.

## Admin dashboard

Sign in using an account whose role is admin, then select Admin dashboard under
Workspace in the sidebar. Employee accounts do not see that navigation, and the
Copilot proxy and Meridian backend independently reject non-admin API requests.

To provision an admin login for an existing employee record, use the local IT
administrator command, replacing the email with the intended administrator:

```bat
cd /d C:\ITSupportCopilot\backend
.venv\Scripts\python scripts\set_user_password.py --email admin@example.com --role admin
```

This sets/resets that account's password, changes its role to admin, and revokes
its old sessions. Use a separate administrator account from your employee test
account. Sign in again after provisioning to receive the updated role.

The dashboard has Overview, Tickets, Employees, and Devices sections. Counts
come from database aggregates rather than the current page. Operational lists
have search, filters, pagination, and refresh controls. Ticket editing supports
normal transitions, priority/reporter/device changes, and reasoned admin status
overrides. History includes the authenticated administrator's employee ID.
Employee records can be created/edited/deactivated; devices can be created,
edited, assigned or unassigned. Login accounts still use the existing account
provisioning process; creating an employee record alone does not set a password.

The Copilot exposes explicit /admin proxy routes. Meridian exposes protected
/admin/summary, /admin/tickets, /admin/employees and /admin/devices queue routes;
existing protected mutation endpoints enforce the business rules. No generic
arbitrary HTTP/SQL proxy is exposed, and dashboard actions do not invoke the LLM.

No PostgreSQL schema migration is required for this dashboard/chat-management
update. Restart both APIs and Streamlit. The conversation metadata table is
created automatically in the existing ignored checkpoint database.
## Choosing a login role

The sign-in page offers Employee login and Admin login. Choose the option matching
the account's company role, enter work email/password, and sign in. Employee
login opens chat; Admin login opens the admin dashboard and retains the Chat
workspace option. The backend checks the selected role against the stored users
record after verifying the password. A mismatch returns 403 before any session is
issued; choosing Admin never upgrades an account. Existing API clients may omit
the optional role field and still authenticate using their stored account role.
No database migration or account-role change is needed for this UI update.
