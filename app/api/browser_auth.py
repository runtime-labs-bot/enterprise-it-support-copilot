"""HttpOnly browser login and a server-authenticated Streamlit session bridge."""
from datetime import datetime, timezone
from functools import lru_cache
import hmac
from html import escape
import os
from pathlib import Path
import secrets
from string import Template
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from app.services.browser_sessions import BrowserSessions, COOKIE_NAME
from app.services.meridian_auth import backend_request

router = APIRouter(prefix="/auth/browser", tags=["Persistent browser login"])
CSRF_COOKIE = "meridian_login_csrf"


def urls():
    ui = os.getenv("COPILOT_PUBLIC_URL", "http://localhost:8501").rstrip("/")
    auth = os.getenv("COPILOT_BROWSER_AUTH_URL", "http://localhost:8001/auth/browser").rstrip("/")
    first, second = urlsplit(ui), urlsplit(auth)
    if not first.hostname or first.scheme not in {"http", "https"} or second.scheme != first.scheme or first.hostname != second.hostname or first.username or second.username:
        raise HTTPException(status_code=503, detail="Browser login requires matching UI/API hostnames and schemes")
    if first.scheme == "http" and first.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=503, detail="Remote browser login requires HTTPS")
    return ui, auth


def secure_cookie():
    return urls()[0].startswith("https://")


@lru_cache
def vault():
    key = os.getenv("BROWSER_SESSION_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Persistent browser login is not configured")
    root = Path(__file__).resolve().parents[2]
    path = root / "data/checkpoints/browser_sessions.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return BrowserSessions(path, key.encode())


def require_ui_key(value):
    expected = os.getenv("BROWSER_UI_AUTH_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Browser session bridge is not configured")
    if not value or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=403, detail="Server session bridge authentication required")


def login_page(role="employee", message="", status=200):
    ui, auth = urls()
    csrf, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    template = Template((Path(__file__).parent / "templates/browser_login.html").read_text(encoding="utf-8"))
    html = template.substitute(nonce=nonce, csrf=csrf, auth=escape(auth, quote=True), message=escape(message), employee="checked" if role != "admin" else "", admin="checked" if role == "admin" else "")
    origin = urlsplit(ui)
    response = HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store", "Referrer-Policy": "same-origin", "Content-Security-Policy": f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; form-action 'self' {origin.scheme}://{origin.netloc}; base-uri 'none'; frame-ancestors {origin.scheme}://{origin.netloc}"})
    response.set_cookie(CSRF_COOKIE, csrf, httponly=True, secure=secure_cookie(), samesite="lax", max_age=600, path="/auth/browser")
    return response


@router.get("/login", response_class=HTMLResponse)
def form(role: Literal["employee", "admin"] = "employee"):
    response = login_page(role)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure_cookie(), samesite="lax")
    return response


@router.post("/login")
def login(request: Request, email: str = Form(max_length=254), password: SecretStr = Form(min_length=1, max_length=128), role: Literal["employee", "admin"] = Form(), csrf: SecretStr = Form(min_length=32, max_length=128), meridian_login_csrf: str | None = Cookie(default=None)):
    ui, auth = urls()
    allowed = {f"{parsed.scheme}://{parsed.netloc}" for parsed in (urlsplit(ui), urlsplit(auth))}
    if request.headers.get("origin") not in allowed or not meridian_login_csrf or not hmac.compare_digest(csrf.get_secret_value(), meridian_login_csrf):
        raise HTTPException(status_code=403, detail="Reload the sign-in page before trying again")
    try:
        tokens = backend_request("/auth/login", method="POST", body={"email": email, "password": password.get_secret_value(), "role": role})
    except HTTPException as error:
        message = "This account cannot use the selected login role." if error.status_code == 403 else "Check your email and password." if error.status_code in {401, 422} else "Sign-in is temporarily unavailable. Please try again."
        return login_page(role, message, error.status_code)
    handle = vault().create(tokens)
    response = RedirectResponse(ui, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    remaining = max(1, int((datetime.fromisoformat(tokens["session_expires_at"]) - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(COOKIE_NAME, handle, httponly=True, secure=secure_cookie(), samesite="lax", max_age=remaining, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/auth/browser", httponly=True, secure=secure_cookie(), samesite="lax")
    return response


class BrowserHandle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: SecretStr = Field(min_length=32, max_length=128)
    force_refresh: bool = False


@router.post("/restore")
def restore(data: BrowserHandle, response: Response, x_ui_auth_key: str | None = Header(default=None)):
    require_ui_key(x_ui_auth_key)
    response.headers["Cache-Control"] = "no-store"
    return vault().restore(data.handle.get_secret_value(), data.force_refresh)


@router.post("/revoke", status_code=204)
def revoke(data: BrowserHandle, x_ui_auth_key: str | None = Header(default=None)):
    require_ui_key(x_ui_auth_key)
    vault().revoke(data.handle.get_secret_value())
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
