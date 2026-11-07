"""Explicit, role-checked dashboard proxy; no arbitrary backend paths."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query, Response
from app.services.meridian_auth import backend_request

router = APIRouter(prefix="/admin", tags=["Admin dashboard"])


def admin_authorization(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    identity = backend_request("/auth/me", authorization=authorization)
    if identity.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return authorization


Admin = Annotated[str, Depends(admin_authorization)]
RecordId = Annotated[int, Path(gt=0, le=2147483647)]
Resource = Literal["tickets", "employees", "devices"]
Editable = Literal["employees", "devices"]
FIELDS = {
    "employees": {"full_name", "email", "department", "job_title", "is_active"},
    "devices": {"asset_tag", "device_type", "manufacturer", "model", "serial_number", "assigned_employee_id"},
    "tickets": {"title", "description", "employee_id", "device_id", "status", "priority", "reason"},
}


def forward(path, authorization, response, *, method="GET", body=None, params=None):
    response.headers["Cache-Control"] = "no-store"
    return backend_request(path, method=method, body=body, params=params, authorization=authorization, allowed_error_detail=True)


def checked_body(resource, data):
    if not data or set(data) - FIELDS[resource]:
        raise HTTPException(status_code=422, detail="Check the required fields and their values")
    return data


@router.get("/summary")
def summary(response: Response, authorization: Admin):
    return forward("/admin/summary", authorization, response)


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int = Field(gt=0, le=2147483647)
    role: Literal["employee", "admin"] = "employee"


@router.post("/setup-invitations", status_code=201)
def setup_invitation(data: InvitationCreate, response: Response, authorization: Admin):
    return forward("/auth/setup-invitations", authorization, response, method="POST", body=data.model_dump())


@router.get("/{resource}")
def records(resource: Resource, response: Response, authorization: Admin,
            offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
            search: str = Query(default="", max_length=200), status: str | None = None, priority: str | None = None,
            employee_id: int | None = Query(default=None, gt=0), assigned_employee_id: int | None = Query(default=None, gt=0), is_active: bool | None = None):
    params = {"offset": offset, "limit": limit, "search": search}
    extra = {"tickets": {"status": status, "priority": priority, "employee_id": employee_id}, "employees": {"is_active": is_active}, "devices": {"assigned_employee_id": assigned_employee_id}}[resource]
    params.update({key: value for key, value in extra.items() if value is not None})
    return forward(f"/admin/{resource}", authorization, response, params=params)


@router.get("/tickets/{record_id}/history")
def ticket_history(record_id: RecordId, response: Response, authorization: Admin, offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    return forward(f"/tickets/{record_id}/history", authorization, response, params={"offset": offset, "limit": limit})


@router.get("/tickets/{record_id}")
def open_ticket(record_id: RecordId, response: Response, authorization: Admin):
    return forward(f"/tickets/{record_id}", authorization, response)


@router.patch("/tickets/{record_id}")
def update_ticket(record_id: RecordId, response: Response, authorization: Admin, data: dict = Body(...)):
    data = dict(data)
    override = data.pop("override", False)
    if type(override) is not bool:
        raise HTTPException(status_code=422, detail="Invalid override option")
    body = checked_body("tickets", data)
    path = f"/tickets/{record_id}" + ("/admin" if override else "")
    return forward(path, authorization, response, method="PATCH", body=body)


@router.post("/{resource}", status_code=201)
def create_record(resource: Editable, response: Response, authorization: Admin, data: dict = Body(...)):
    return forward(f"/{resource}", authorization, response, method="POST", body=checked_body(resource, data))


@router.patch("/{resource}/{record_id}")
def update_record(resource: Editable, record_id: RecordId, response: Response, authorization: Admin, data: dict = Body(...)):
    return forward(f"/{resource}/{record_id}", authorization, response, method="PATCH", body=checked_body(resource, data))
