# Run the complete stack with Docker Compose

Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) with Linux containers. Compose 2.17 or newer and BuildKit are required for the additional backend build context. Keep the two repositories next to each other:

```text
C:\ITSupportCopilot
C:\MeridianITBackend
```

The Compose file belongs to the Copilot repository. Meridian's Dockerfile and migrations remain in its own repository. To use a different location, set `MERIDIAN_BUILD_CONTEXT` to a forward-slash path in `.env.docker`.

## First start (CMD)

Stop the locally running backend, Copilot API, and Streamlit with Ctrl+C to free ports 8000, 8001, and 8501. The local PostgreSQL Windows service can stay running; container PostgreSQL does not publish a host port.

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python scripts\init_docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d --wait
docker compose --env-file .env.docker ps -a
```

The initialization script copies only existing Groq/Pinecone/Tavily configuration and generates independent database, JWT, admin, and support credentials in ignored `.env.docker`. It does not display secrets or change your local `.env`. If any provider key is missing, fill it in `.env.docker` before starting. Re-running initialization preserves the file; do not regenerate credentials for an existing database volume.

If another process or Docker stack occupies the default ports, add or update these entries in `.env.docker` (one entry per name):

```dotenv
MERIDIAN_PORT=8002
STREAMLIT_PORT=8502
COPILOT_PUBLIC_URL=http://localhost:8502
```

Then run `docker compose --env-file .env.docker up -d --wait`. Meridian will be at `http://localhost:8002/docs` and the UI at `http://localhost:8502`. Internal service addresses stay unchanged. Add `--public-url http://localhost:8502` to the admin setup command below when using this UI port. `COPILOT_PORT` can similarly change the API's host port if 8001 is occupied. Do not terminate Docker or WSL processes to free ports.

PostgreSQL becomes healthy first, `migrate` runs Alembic and exits successfully, Meridian becomes healthy, then the Copilot API and Streamlit start. An exited `migrate` container with code 0 is expected. Health-based dependencies follow [Docker's startup ordering](https://docs.docker.com/compose/how-tos/startup-order/).

## Create your first admin without entering a password in the terminal

The Docker database starts empty. Your existing Windows employees, accounts, tickets, and chats are not automatically imported.

```bat
docker compose --env-file .env.docker exec meridian python scripts/create_admin_setup.py --email rd02@example.com --full-name RD02
```

Open the private activation URL printed by this command, set your password in the browser, then sign in using **Admin login**. The link is an admin credential until used: share it only with the intended account owner. It expires after 24 hours. Existing logins are preserved; the command refuses to reset or promote them. This is a trusted container administration command, not a public signup API.

Use **Admin dashboard → Employees** to create employees and issue their individual setup links. Set `COPILOT_PUBLIC_URL` in `.env.docker` to the browser-visible URL if using a different UI port. The default Compose ports bind only to localhost; remote hosting additionally requires an appropriate network and HTTPS setup.

## Services and storage

| Service | Address | Persistent storage |
| --- | --- | --- |
| Streamlit | http://localhost:8501 | Session state is temporary |
| Copilot API | http://localhost:8001/docs | `copilot_checkpoints` volume |
| Meridian API | http://localhost:8000/docs | PostgreSQL |
| PostgreSQL 18 | Internal `postgres:5432` | `postgres_data` volume |

The PostgreSQL volume mounts `/var/lib/postgresql`, following the [official PostgreSQL 18 image layout](https://hub.docker.com/_/postgres). Both volumes survive container recreation and ordinary `docker compose down`. Removing volumes deletes the corresponding container data. Keep backups before any database migration or volume removal.

The MCP bridge runs on demand as a stdio subprocess in the Copilot container using Python at `/usr/local/bin/python` and Meridian code at `/opt/meridian`. It calls `http://meridian:8000` and carries the authenticated user's token. It receives no admin or support service key. Streamlit receives no model-provider or database credentials. Application containers run as a non-root user.

## Check and manage the stack

```bat
curl http://localhost:8000/health/database
curl http://localhost:8001/
curl http://localhost:8501/_stcore/health
docker compose --env-file .env.docker logs --tail=100 migrate meridian copilot streamlit
docker compose --env-file .env.docker down
docker compose --env-file .env.docker up -d --wait
```

After logging in as an employee, create a ticket through chat, sign out and back in, and verify the conversation is restored. Close your own ticket through chat; use the admin dashboard for support status changes. After `down` and `up`, confirm both the ticket and saved conversation remain. Rebuild with `up --build -d --wait` after source changes; `restart` alone does not rebuild images or update environment configuration. Always use `--env-file .env.docker`. Avoid displaying full resolved Compose configuration because it includes credentials; use `config --quiet` for validation.

This setup creates an isolated development database. Migrating the existing Windows database and checkpoints requires a separate backup/restore step; it has not been performed automatically.
