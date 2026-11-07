from datetime import datetime, timezone
import hashlib
import json
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Device, Employee, Ticket, TicketStatusHistory, TicketCreateRequest
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.security import Operator

TRANSITIONS = {"open": {"in_progress"}, "in_progress": {"resolved"}, "resolved": {"in_progress", "closed"}, "closed": set()}


class LinkedRecordNotFoundError(Exception):
    pass


class WorkflowConflictError(Exception):
    pass


class EmployeeActionDeniedError(Exception):
    pass


class AdminRequiredError(Exception):
    pass


def _check_links(db: Session, values: dict):
    for field, model, label in (("employee_id", Employee, "Employee"), ("device_id", Device, "Device")):
        record_id = values.get(field)
        if record_id is not None and db.get(model, record_id) is None:
            raise LinkedRecordNotFoundError(f"{label} not found")


def _integrity_error(db: Session, exc: IntegrityError):
    db.rollback()
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if getattr(exc.orig, "sqlstate", None) == "23503":
        if constraint == "fk_tickets_employee":
            raise LinkedRecordNotFoundError("Employee not found") from None
        if constraint == "fk_tickets_device":
            raise LinkedRecordNotFoundError("Device not found") from None
    raise exc


def _save(db: Session, ticket: Ticket):
    try:
        db.commit()
    except IntegrityError as exc:
        _integrity_error(db, exc)
    db.refresh(ticket)
    return ticket


def create_ticket(db: Session, data: TicketCreate, operator: Operator, idempotency_key: str | None = None):
    values = data.model_dump()
    if operator.role == "employee" and values["employee_id"] != operator.employee_id:
        raise EmployeeActionDeniedError("You can create tickets only for yourself")
    reservation = None
    if idempotency_key is not None:
        scope = f'{operator.role}:user:{operator.user_id}' if operator.user_id else f'{operator.role}:employee:{operator.employee_id}'
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        payload_hash = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        # Unique insertion blocks competing requests until the winning transaction
        # commits or rolls back. A crash cannot leave a committed empty reservation.
        inserted = db.scalar(insert(TicketCreateRequest).values(actor_scope=scope, key_hash=key_hash, payload_hash=payload_hash).on_conflict_do_nothing().returning(TicketCreateRequest.key_hash))
        reservation = db.get(TicketCreateRequest, (scope, key_hash))
        if inserted is None:
            if reservation.payload_hash != payload_hash:
                raise WorkflowConflictError('Idempotency key was already used for different ticket details')
            existing = db.get(Ticket, reservation.ticket_id) if reservation.ticket_id else None
            if existing is None:
                raise WorkflowConflictError('The original ticket was deleted; use a new key for a new ticket')
            if operator.role == 'employee' and existing.employee_id != operator.employee_id:
                raise EmployeeActionDeniedError('The original ticket is no longer assigned to you')
            return existing
    _check_links(db, values)
    ticket = Ticket(**values)
    _record_review(ticket, operator)
    db.add(ticket)
    try:
        db.flush()  # Obtain the ID in the same transaction as its creation event.
    except IntegrityError as exc:
        _integrity_error(db, exc)
    db.add(TicketStatusHistory(ticket_id=ticket.id, old_status=None, new_status="open", actor_role=operator.role, actor_employee_id=operator.employee_id, reason="Ticket created"))
    if reservation is not None:
        reservation.ticket_id = ticket.id
    return _save(db, ticket)


def list_tickets(db: Session, offset: int, limit: int, **filters):
    query = select(Ticket).order_by(Ticket.id)
    for field, value in filters.items():
        if value is not None:
            query = query.where(getattr(Ticket, field) == value)
    return db.scalars(query.offset(offset).limit(limit)).all()


def get_ticket(db: Session, ticket_id: int):
    return db.get(Ticket, ticket_id)


def _locked_ticket(db, ticket_id):
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update().execution_options(populate_existing=True))
    if ticket is None:
        raise LinkedRecordNotFoundError("Ticket not found")
    return ticket


def _record_review(ticket, operator):
    if operator.role == "admin" and ticket.reviewed_at is None:
        ticket.reviewed_at = datetime.now(timezone.utc)
        ticket.reviewed_by_employee_id = operator.employee_id
        return True
    return False


def open_ticket(db, ticket, operator):
    if operator.role != "admin":
        return ticket
    ticket = _locked_ticket(db, ticket.id)
    return _save(db, ticket) if _record_review(ticket, operator) else ticket


def update_ticket(db: Session, ticket: Ticket, data: TicketUpdate, operator: Operator, admin_override: bool = False):
    values = data.model_dump(exclude_unset=True)
    reason = values.pop("reason", None)
    if operator.role == "employee":
        if values == {"status": "closed"}:
            return close_ticket(db, ticket, operator)
        if not values or set(data.model_fields_set) - {"title", "description"}:
            raise EmployeeActionDeniedError("Employees may edit only their own unreviewed ticket title/description, or close their own ticket")
        ticket = _locked_ticket(db, ticket.id)
        if ticket.employee_id != operator.employee_id:
            raise EmployeeActionDeniedError("You can edit only your own ticket")
        if ticket.reviewed_at is not None:
            raise WorkflowConflictError("An administrator has already reviewed this ticket. Its details are locked. Create a new ticket to add details or clarify the issue.")
        if ticket.status != "open":
            raise WorkflowConflictError("Only an open, unreviewed ticket can be edited. Create a new ticket to add details or clarify the issue.")
        for field, value in values.items():
            setattr(ticket, field, value)
        return _save(db, ticket)
    # Status is privileged even if a caller submits the current value.
    if "status" in values and operator.role != "admin":
        raise AdminRequiredError
    # Serialize transitions and reload any stale ORM instance after acquiring the lock.
    ticket = _locked_ticket(db, ticket.id)
    if admin_override and operator.role != "admin":
        raise AdminRequiredError
    if operator.role != "admin" and any(field in values and values[field] != getattr(ticket, field) for field in ("employee_id", "priority")):
        raise AdminRequiredError
    new_status = values.get("status", ticket.status)
    old_status = ticket.status
    if new_status != old_status:
        normal = new_status in TRANSITIONS[old_status]
        if admin_override or not normal:
            if operator.role != "admin":
                raise WorkflowConflictError(f"Cannot change status from {old_status} to {new_status}")
            if not reason:
                raise WorkflowConflictError("A reason is required for an administrator status override")
    _check_links(db, values)
    _record_review(ticket, operator)
    for field, value in values.items():
        setattr(ticket, field, value)
    if new_status != old_status:
        db.add(TicketStatusHistory(ticket_id=ticket.id, old_status=old_status, new_status=new_status, actor_role=operator.role, actor_employee_id=operator.employee_id, reason=reason))
    return _save(db, ticket)


def get_status_history(db: Session, ticket_id: int, offset: int, limit: int):
    return db.scalars(select(TicketStatusHistory).where(TicketStatusHistory.ticket_id == ticket_id).order_by(TicketStatusHistory.id).offset(offset).limit(limit)).all()


def delete_ticket(db: Session, ticket: Ticket, operator: Operator):
    if operator.role != "admin":
        raise AdminRequiredError
    db.delete(ticket)
    db.commit()


def close_ticket(db: Session, ticket: Ticket, operator: Operator):
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket.id).with_for_update().execution_options(populate_existing=True))
    if ticket is None:
        raise LinkedRecordNotFoundError("Ticket not found")
    if operator.role != "employee" or ticket.employee_id != operator.employee_id:
        raise EmployeeActionDeniedError("Only the reporting employee can use self-service closure")
    if ticket.status == "closed":
        return ticket
    old_status = ticket.status
    ticket.status = "closed"
    reason = "Reporter confirmed the issue is resolved" if old_status == "resolved" else "Reporter fixed the issue and closed the ticket without awaiting support resolution"
    db.add(TicketStatusHistory(ticket_id=ticket.id, old_status=old_status, new_status="closed", actor_role="employee", actor_employee_id=operator.employee_id, reason=reason))
    return _save(db, ticket)
