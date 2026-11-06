# Combined repository

`enterprise-it-support-copilot` is the main repository for both services. Meridian
was imported into `backend/` from commit `f6adc97` of `meridian-it-backend`.
The original repository remains available as historical source; the application
no longer requires that checkout. Its Git metadata, virtual environment, private
setup links, and credentials are not part of the import.

AI code remains in `app/agent`, with the Copilot HTTP API in `app/api` and UI in
`ui/`. Both services keep their existing Python `app` package. Separate working
directories, interpreters, and subprocesses isolate imports. Meridian's
configuration resolves from `backend/.env`; Copilot resolves its local backend
path from the repository root. Docker bundles the MCP bridge at `/opt/meridian`
and calls the Meridian service over HTTP.

For an existing local checkout, create `backend/.venv`, install
`backend/requirements-dev.txt`, preserve the old backend configuration privately
in `backend/.env`, and set the root `.env` value `MERIDIAN_BACKEND_DIR=backend`.
Do not commit either environment file. Local database contents and credentials
do not need to change. New installations can follow [backend setup](../backend/README.md).

Docker uses the same project name, service names, PostgreSQL volume, and
checkpoint volume. Keep `.env.docker` and its port overrides. Rebuild with
`docker compose --env-file .env.docker up --build -d --wait`; no volume removal
or database reset is needed.

## Verification

- `python scripts/test_all.py`: 50 Copilot tests and 76 backend tests passed.
- `python scripts/verify_meridian.py`: real MCP/REST/PostgreSQL workflow,
  authentication, dashboard, conversation rename/archive/restore, and cleanup passed.
- Combined Docker images built successfully; all four services are healthy,
  and the migration job exited with code 0.
- `python scripts/verify_compose.py --live-model`: browser password setup APIs,
  role permissions, device lookup, MCP ticket creation, admin resolution, employee
  closure, actor history, live Groq/LangGraph/MCP lookup, logout revocation, and
  chat restoration after fresh login passed in the running containers.

The verification uses generated fixture credentials and removes temporary
business records. No real user password is changed. The Docker UI remains at
the configured address, currently `http://localhost:8502` on this installation.
