# Admin chat

Sign in using **Admin login**. The app now opens **Admin chat** by default;
the sidebar still offers the dashboard. Employee chat keeps its restricted tools.
The server obtains the role from authenticated backend identity, never chat text.

Admin chat supports:

| Dashboard feature | Example request |
| --- | --- |
| Overview totals | Show dashboard totals and high-priority active tickets. |
| Employee search | Find employee KD and show whether they are active. |
| Create employee | Create employee Jane Doe, jane@example.com, department Finance. |
| Edit/deactivate/reactivate | Deactivate employee 42. / Reactivate that employee. |
| Device search | Find laptop MER-LAP-001 and show its assignment. |
| Create device | Add laptop MER-LAP-002, manufacturer HP, model Example. |
| Edit/assign/unassign device | Assign device 19 to employee 42. / Unassign device 19. |
| Ticket queues | Show open, high-priority tickets for employee 42. |
| Ticket creation | Create a ticket for employee 42: VPN connection fails after login. |
| Ticket updates | Move ticket 29 to in_progress and set priority high. |
| Workflow overrides | Override ticket 29 to open; reason: employee reported the problem again. |
| Status history | Show the status history for ticket 29. |
| Login activation links | Prepare an employee login setup link for employee 42. |

For ambiguous names, supply an exact employee/device/ticket ID. The assistant
must look up records and ask for missing required details rather than invent them.
Passwords and API keys are not chat inputs. The chat covers dashboard actions;
permanent deletion and arbitrary HTTP requests are not exposed.

## Review before execution

Every admin mutation creates a review card in the current conversation. It shows
the target record, requested changes, workflow override flag/reason when applicable,
and expiry. Select **Confirm action** or **Cancel action**. A proposed change has
not yet run. Cards expire after ten minutes and are scoped to the verified account
and conversation. A new proposal replaces an earlier pending proposal in that chat.

On confirmation the API verifies admin identity again and executes the saved,
allowlisted action through the protected backend routes. It checks the record's
last update against the preview and rejects a stale preview. This is a preflight
check, not an atomic database compare-and-swap across concurrent writers.
An atomic SQLite claim prevents duplicate confirmation requests from executing
the same action twice. After a network/server failure or interrupted execution,
the action is not automatically retried: inspect the target record before making
a fresh request. Backend ownership, foreign keys and workflow rules remain active.

Confirmed public results are appended to the saved conversation so follow-up
requests can refer to the updated record. Pending/attempted actions are stored in
the existing checkpoint volume. Credentials are never saved with actions.
Opening a specific ticket records its first admin review and locks employee
title/description edits. Queue browsing does not mark review. See the
[ticket review rules](ticket-review.md).
Successful setup-link generation returns its token only once to the confirmation
UI. The UI displays a private link that can be copied and shared with the intended
employee; it is excluded from model context and saved chat/action results. If the
link is lost, request a new setup link, which invalidates the earlier invitation.

## Verification

```bat
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python scripts\verify_meridian.py
.venv\Scripts\python scripts\verify_compose.py --live-admin
```

The first command covers tool filtering, proposal validation, explicit controls,
ownership, expiry/cancellation, stale records, duplicate confirmations and private
token handling. The second scripts model planning while executing every action
type through real backend authentication/REST/PostgreSQL, and tests real MCP
admin read tools. The third uses the real model in Docker to prepare deactivation
and a contextual reactivation of a temporary employee, confirms both changes,
and checks employee denial. Temporary business records are removed afterward.
