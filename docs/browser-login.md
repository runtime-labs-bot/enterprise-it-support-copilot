# Login persists through browser refresh

Streamlit creates a new server session after a full page refresh. The application
now restores authentication through a browser cookie. It uses the documented
[Streamlit cookie context](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.context)
and [FastAPI response cookies](https://fastapi.tiangolo.com/advanced/response-cookies/).

Sign in once after updating: choose **Continue to sign in**, then use the normal
browser form served by the Copilot API. Successful login sets a persistent HttpOnly, SameSite=Lax
cookie and redirects back to Copilot. The cookie holds an unpredictable session
handle, not a JWT, refresh token, password, or API key. It expires with the backend
session (seven days by default).

On refresh or a fresh tab, Streamlit reads the request cookie and uses a
server-authenticated bridge to restore login. The backend rechecks account/session
state, returns the current role/profile, and rotates refresh credentials when
needed. Normal account-scoped chat history is restored.

## Storage and revocation

Credentials are Fernet-encrypted in a separate `browser_sessions.sqlite` file
inside the existing checkpoint volume. Only a SHA-256 hash of the browser handle
is stored. The encryption key is in the ignored environment file. No token goes
into URLs, localStorage, model context, or saved chat. The restore bridge requires
its own server secret, preventing public requests from retrieving stored JWTs.

Refresh rotation is serialized across tabs in the dedicated session database,
without locking chat history. A refresh whose response is lost can still require
login again because the backend rejects replayed refresh credentials.

Sign out revokes the browser handle and backend login family. Other tabs lose
access on their next authenticated operation or refresh. If the backend is down
during logout, the local handle is still revoked and the UI reports unconfirmed
server revocation. Expired, revoked, reset, or inactive backend logins cannot be
restored. Transient outages offer retry instead of discarding a valid saved login.

The form uses Origin checks and a short-lived double-submit CSRF nonce. Passwords
are submitted by POST and never echoed on errors. Cookies use Secure on HTTPS;
plain HTTP is allowed only on loopback development hosts. Always sign out on
shared computers.

## Docker configuration

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python scripts\init_docker_env.py
docker compose --env-file .env.docker up --build -d --wait
```

Initialization adds missing `DOCKER_BROWSER_SESSION_KEY` and
`DOCKER_BROWSER_UI_AUTH_KEY` while preserving existing credentials and ports.
Never regenerate these keys on ordinary startup.

`COPILOT_PUBLIC_URL` is the browser's Streamlit address, currently
`http://localhost:8502`. `COPILOT_BROWSER_AUTH_URL` defaults to
`http://localhost:8001/auth/browser`; change it if the public API port changes.
Both URLs must use the same hostname and scheme: use `localhost` consistently,
rather than mixing it with `127.0.0.1`. Cookies are scoped to hosts, not ports.
Remote hosting requires HTTPS and correctly configured public API/proxy URLs.
Private `API_URL` stays `http://copilot:8001/ask`.

For non-Docker runs, set `BROWSER_SESSION_KEY` on the API, share
`BROWSER_UI_AUTH_KEY` between API/Streamlit, and configure both public URLs.
Without these settings the original session-only form remains for development.

## Browser verification

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts\verify_browser_login.py
```

The check uses separate headless Chrome contexts and generated employee/admin
accounts. It verifies login, Show password, repeated refreshes, a fresh context,
HttpOnly cookie visibility, and cross-context logout. It writes no browser cookie
files, changes no real user passwords, and removes temporary accounts afterward.
