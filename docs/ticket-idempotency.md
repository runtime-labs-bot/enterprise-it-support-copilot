# Ticket creation idempotency

`POST /tickets` accepts an optional `Idempotency-Key` header (1–128 ASCII letters,
digits, dots, underscores, colons or hyphens). Use a new random UUID for each
intentional new ticket and reuse it for retries of that request. Existing clients
without a key still work, but do not get cross-request deduplication.

The key is scoped to the authenticated actor. PostgreSQL stores hashes of the key
and normalized validated payload in `ticket_create_requests`. Its composite
primary key serializes concurrent identical requests. The reservation, ticket,
and initial status event commit in the same transaction; failures roll back all
three. A replay returns the same ticket ID with its current representation and
HTTP 201, without adding history or marking admin review again.

- Reusing the key with different validated details returns 409.
- Different employees may safely use the same key without sharing records.
- If the ticket was reassigned, its former reporting employee receives 403.
- Deletion leaves a key tombstone; replay returns 409 rather than recreating it.
- Reservations do not expire automatically. Raw keys and ticket content are not
  stored in this table. A deliberate new request must use a new key.

The Copilot `/ask` API accepts `request_id` alongside `thread_id`. Keep both values
stable when retrying a request. The Streamlit client generates the request ID and
reuses it for its authentication-refresh retry. The request ID is returned in the
API response. The trusted runtime derives the MCP key from the message identity;
the key is hidden from the model tool schema and model-supplied keys are ignored.
One chat request can create one distinct ticket; ask separately to create another.
If the model changes the payload on replay, the backend returns a conflict.
Confirmed admin chat creation uses its persisted action ID as the backend key.

This protects retries with stable identities, not semantic similarity. Repeating
the same text as a new chat request creates a new intent and may create another
ticket. Uncertain writes are still not retried automatically. User permissions
are checked on every request, including replays.

Apply migration `0009_ticket_idempotency` before running the changed backend:

```bat
cd /d C:\ITSupportCopilot\backend
.venv\Scripts\python.exe -m alembic upgrade head
```

For Docker, rebuild/start normally; the existing migration service applies it:

```bat
cd /d C:\ITSupportCopilot
docker compose --env-file .env.docker up --build -d --wait
```

Both the local development database and the rebuilt Docker database are now at
migration `0009_ticket_idempotency`. PostgreSQL tests cover
replay across logins, changed payloads, ownership, rollback, deletion, reassignment,
invalid keys, independent concurrent sessions, and MCP header propagation.
`scripts/verify_docker_safeguards.py` additionally verified the running Docker
HTTP endpoint with disposable accounts and tickets, then removed the fixtures.
