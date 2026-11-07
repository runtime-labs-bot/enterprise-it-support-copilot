# Employee ticket editing before admin review

Employees may update the title and description of their own ticket while it is
**open and unreviewed**. In chat, provide the ticket ID or a clear conversation
reference and the replacement text, for example:

- `Update ticket 29's description to: The VPN fails on office Wi-Fi but works on my hotspot.`
- `Change the title of ticket 29 to: VPN fails on office Wi-Fi.`

If the employee only says `edit description`, the assistant asks for the new text.
It does not invent details or create another ticket automatically.

Opening an individual ticket using the admin dashboard, admin chat `get_ticket`,
or authenticated backend `GET /tickets/{id}` records the first review. Any admin
ticket update also records review, even without a prior read. An admin-created
ticket is already reviewed. The first timestamp/actor is retained on later reads.
Browsing/searching a queue, viewing status history alone, and employee reads do
not mark review. Opening the selected dashboard ticket performs a detail read.

After review, employee content edits receive HTTP 409 and an explanation that a
**new ticket is required for additional details or clarification**. Existing
details remain unchanged. Title/description edits to closed tickets are also
blocked. Employees cannot change priority, reporter, device assignment, general
status, or review metadata. They can still close their own open, in-progress or
resolved ticket after fixing the issue. Admins retain their edit permissions.

Responses include `reviewed_at`, `reviewed_by_employee_id`, and
`employee_can_edit`. The flag describes the reporter's content-edit window;
authentication and ownership are checked separately on every request. Internal
admin service keys can mark review without an employee actor ID. No endpoint
allows clearing the review fields to reopen employee edits.

The backend serializes admin first-review marking and employee editing using
the same PostgreSQL ticket-row lock and reloads stale ORM state after locking.
If the admin review wins the race, the employee edit is rejected. If the edit
commits first, the admin receives those latest details and locks subsequent edits.
Content edits do not generate misleading status-history transitions.

Migration `0008_ticket_review_lock` adds the nullable review fields. Existing
admin status-history entries provide evidence for a backfilled first review.
Old read-only admin views were not recorded, so those historical views cannot be
reconstructed; open tickets without recorded admin actions start unreviewed.
Migration preserves all ticket details and status history.

```bat
cd /d C:\ITSupportCopilot
docker compose --env-file .env.docker up --build -d --wait
.venv\Scripts\python scripts\verify_compose.py
```

The Compose migration job applies the schema update before starting the new API.
The integration check verifies employee edits before review, non-locking queues,
locking admin opens, rejection afterward, and continued self-service closure.
