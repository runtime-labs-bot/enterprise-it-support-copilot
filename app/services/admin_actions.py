"""Reviewed admin commands. No credentials or activation tokens are persisted."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.services.meridian_auth import backend_request

FIELDS = {
    "create_employee": {"full_name", "email", "department", "job_title", "is_active"},
    "update_employee": {"full_name", "email", "department", "job_title", "is_active"},
    "create_device": {"asset_tag", "device_type", "manufacturer", "model", "serial_number", "assigned_employee_id"},
    "update_device": {"asset_tag", "device_type", "manufacturer", "model", "serial_number", "assigned_employee_id"},
    "update_ticket": {"title", "description", "employee_id", "device_id", "status", "priority", "reason"},
    "create_ticket": {"title", "description", "employee_id", "device_id", "priority"},
    "setup_login": {"role"},
}


class AdminAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create_employee", "update_employee", "create_device", "update_device", "create_ticket", "update_ticket", "setup_login"]
    record_id: int | None = Field(default=None, gt=0, le=2147483647)
    changes: dict = Field(min_length=1, max_length=12)
    override: bool = False

    @model_validator(mode="after")
    def allowed_changes(self):
        if set(self.changes) - FIELDS[self.operation]:
            raise ValueError("Unsupported fields")
        create = self.operation.startswith("create_")
        if create != (self.record_id is None):
            raise ValueError("Existing record ID is required only for updates/setup")
        required = {"create_employee": {"full_name", "email"}, "create_device": {"asset_tag", "device_type"}, "create_ticket": {"title", "description", "employee_id"}, "setup_login": {"role"}}.get(self.operation, set())
        if not required <= self.changes.keys():
            raise ValueError("Required fields are missing")
        nullable = {"department", "job_title", "manufacturer", "model", "serial_number", "assigned_employee_id", "device_id", "reason"}
        for key, value in self.changes.items():
            if key == "is_active":
                valid = type(value) is bool
            elif key in {"employee_id", "device_id", "assigned_employee_id"}:
                valid = (type(value) is int and 0 < value <= 2147483647) or (key in nullable and value is None)
            else:
                valid = (isinstance(value, str) and bool(value.strip()) and len(value) <= 10000) or (key in nullable and value is None)
            if not valid:
                raise ValueError("Invalid field value")
        if self.operation == "setup_login" and self.changes["role"] not in {"employee", "admin"}:
            raise ValueError("Invalid login role")
        if self.override and (self.operation != "update_ticket" or not self.changes.get("reason", "").strip()):
            raise ValueError("Ticket overrides require a reason")
        return self

    def endpoint(self):
        resource = "employees" if "employee" in self.operation or self.operation == "setup_login" else "devices" if "device" in self.operation else "tickets"
        return resource


class AdminActionStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS admin_chat_actions (id TEXT PRIMARY KEY, scope TEXT NOT NULL, thread_id TEXT NOT NULL, plan TEXT NOT NULL, before_json TEXT, status TEXT NOT NULL, expires_at TEXT NOT NULL, result_json TEXT)")

    def connection(self):
        # sqlite Connection context commits, but does not close: use a wrapper.
        from contextlib import contextmanager
        @contextmanager
        def opened():
            with closing(sqlite3.connect(self.path, timeout=15)) as db:
                db.row_factory = sqlite3.Row
                with db:
                    yield db
        return opened()

    def public(self, row):
        return {"id": row["id"], "thread_id": row["thread_id"], "plan": json.loads(row["plan"]), "before": json.loads(row["before_json"]) if row["before_json"] else None, "status": row["status"], "expires_at": row["expires_at"], "result": json.loads(row["result_json"]) if row["result_json"] else None}

    def propose(self, scope, thread_id, plan, authorization):
        action = AdminAction.model_validate(plan)
        before = None
        if action.record_id:
            row = backend_request(f"/{action.endpoint()}/{action.record_id}", authorization=authorization, allowed_error_detail=True)
            before = {key: row.get(key) for key in {"id", "full_name", "email", "asset_tag", "title", "status", "updated_at", *action.changes.keys()}}
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        action_id = uuid4().hex
        with self.connection() as db:
            db.execute("UPDATE admin_chat_actions SET status='cancelled' WHERE scope=? AND thread_id=? AND status='pending'", (scope, thread_id))
            db.execute("INSERT INTO admin_chat_actions VALUES (?,?,?,?,?,'pending',?,NULL)", (action_id, scope, thread_id, action.model_dump_json(), json.dumps(before) if before else None, expires))
        return self.get(scope, thread_id, action_id)

    def get(self, scope, thread_id, action_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM admin_chat_actions WHERE id=? AND scope=? AND thread_id=?", (action_id, scope, thread_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Admin action not found")
        return self.public(row)

    def list(self, scope, thread_id):
        with self.connection() as db:
            db.execute("UPDATE admin_chat_actions SET status='expired' WHERE scope=? AND thread_id=? AND status='pending' AND expires_at<=?", (scope, thread_id, datetime.now(timezone.utc).isoformat()))
            rows = db.execute("SELECT * FROM admin_chat_actions WHERE scope=? AND thread_id=? AND status IN ('pending','executing','uncertain') ORDER BY rowid DESC LIMIT 10", (scope, thread_id)).fetchall()
        return [self.public(row) for row in rows]

    def cancel(self, scope, thread_id, action_id):
        with self.connection() as db:
            db.execute("UPDATE admin_chat_actions SET status='cancelled' WHERE id=? AND scope=? AND thread_id=? AND status='pending'", (action_id, scope, thread_id))
        return self.get(scope, thread_id, action_id)

    def confirm(self, scope, thread_id, action_id, authorization):
        with self.connection() as db:
            changed = db.execute("UPDATE admin_chat_actions SET status='executing' WHERE id=? AND scope=? AND thread_id=? AND status='pending' AND expires_at>?", (action_id, scope, thread_id, datetime.now(timezone.utc).isoformat())).rowcount
        stored = self.get(scope, thread_id, action_id)
        if not changed:
            if stored["status"] == "completed":
                return {"action": stored, "result": stored["result"]}
            raise HTTPException(status_code=409, detail="This action is expired, cancelled, or already attempted. Check records before requesting another change.")
        action = AdminAction.model_validate(stored["plan"])
        try:
            if stored["before"]:
                current = backend_request(f"/{action.endpoint()}/{action.record_id}", authorization=authorization)
                if current.get("updated_at") != stored["before"].get("updated_at"):
                    raise HTTPException(status_code=409, detail="The record changed after this preview. Request a fresh preview.")
            if action.operation == "setup_login":
                raw = backend_request("/auth/setup-invitations", method="POST", body={"employee_id": action.record_id, **action.changes}, authorization=authorization, allowed_error_detail=True)
                private_token = raw.pop("token")
                result = {"operation": action.operation, "record": raw, "message": "Setup link issued. It is shown privately once; it is not saved in chat."}
            else:
                private_token = None
                path = f"/{action.endpoint()}" + (f"/{action.record_id}" if action.record_id else "") + ("/admin" if action.override else "")
                record = backend_request(path, method="POST" if action.operation.startswith("create_") else "PATCH", body=action.changes, authorization=authorization, allowed_error_detail=True)
                result = {"operation": action.operation, "record": record}
        except HTTPException as error:
            status = "uncertain" if error.status_code >= 500 else "failed"
            with self.connection() as db:
                db.execute("UPDATE admin_chat_actions SET status=? WHERE id=?", (status, action_id))
            raise
        except Exception:
            with self.connection() as db:
                db.execute("UPDATE admin_chat_actions SET status='uncertain' WHERE id=?", (action_id,))
            raise HTTPException(status_code=503, detail="The action outcome is uncertain. Check the record before trying again.") from None
        with self.connection() as db:
            db.execute("UPDATE admin_chat_actions SET status='completed', result_json=? WHERE id=?", (json.dumps(result), action_id))
        response = {"action": self.get(scope, thread_id, action_id), "result": result}
        if private_token:
            response["private_setup_token"] = private_token
        return response
