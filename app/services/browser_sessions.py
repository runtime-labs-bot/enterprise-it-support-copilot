"""Encrypted server-side login vault addressed by opaque browser cookies."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import sqlite3
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from app.services.meridian_auth import backend_request

COOKIE_NAME = "meridian_browser_session"


class BrowserSessions:
    def __init__(self, path, key):
        self.path = str(path)
        self.cipher = Fernet(key)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS browser_sessions (handle_hash TEXT PRIMARY KEY, encrypted_tokens BLOB NOT NULL, expires_at TEXT NOT NULL)")
            db.commit()

    @staticmethod
    def digest(handle):
        return hashlib.sha256(handle.encode()).hexdigest()

    def create(self, tokens):
        handle = secrets.token_urlsafe(48)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DELETE FROM browser_sessions WHERE expires_at<=?", (datetime.now(timezone.utc).isoformat(),))
            db.execute("INSERT INTO browser_sessions VALUES (?,?,?)", (self.digest(handle), self.cipher.encrypt(json.dumps(tokens).encode()), tokens["session_expires_at"]))
            db.commit()
        return handle

    def restore(self, handle, force_refresh=False):
        # Serialize refresh rotation across tabs/processes in a dedicated database,
        # without holding locks on the chat/checkpoint database during HTTP calls.
        with closing(sqlite3.connect(self.path, timeout=35)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT encrypted_tokens,expires_at FROM browser_sessions WHERE handle_hash=?", (self.digest(handle),)).fetchone()
            if row is None:
                raise HTTPException(status_code=401, detail="Browser session ended")
            try:
                if datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
                    raise ValueError("Expired")
                tokens = json.loads(self.cipher.decrypt(row[0]))
                refresh = force_refresh or datetime.fromisoformat(tokens["expires_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=30)
                if not refresh:
                    try:
                        tokens["user"] = backend_request("/auth/me", authorization="Bearer " + tokens["access_token"])
                    except HTTPException as error:
                        if error.status_code != 401:
                            raise
                        refresh = True
                if refresh:
                    tokens = backend_request("/auth/refresh", method="POST", body={"refresh_token": tokens["refresh_token"]})
            except (InvalidToken, ValueError, KeyError, TypeError):
                db.execute("DELETE FROM browser_sessions WHERE handle_hash=?", (self.digest(handle),))
                db.commit()
                raise HTTPException(status_code=401, detail="Browser session ended") from None
            except HTTPException as error:
                if error.status_code == 401:
                    db.execute("DELETE FROM browser_sessions WHERE handle_hash=?", (self.digest(handle),))
                    db.commit()
                raise
            db.execute("UPDATE browser_sessions SET encrypted_tokens=?,expires_at=? WHERE handle_hash=?", (self.cipher.encrypt(json.dumps(tokens).encode()), tokens["session_expires_at"], self.digest(handle)))
            db.commit()
            return tokens

    def revoke(self, handle):
        with closing(sqlite3.connect(self.path, timeout=35)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT encrypted_tokens FROM browser_sessions WHERE handle_hash=?", (self.digest(handle),)).fetchone()
            db.execute("DELETE FROM browser_sessions WHERE handle_hash=?", (self.digest(handle),))
            db.commit()
        if row is not None:
            try:
                refresh = json.loads(self.cipher.decrypt(row[0]))["refresh_token"]
            except (InvalidToken, ValueError, KeyError):
                return
            backend_request("/auth/logout", method="POST", body={"refresh_token": refresh})
