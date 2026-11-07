"""PostgreSQL request replay, atomic rollback and independent-client races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import AsyncMock, patch
import os
import httpx
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
import test_auth
from app.database import engine
from app.models import Employee, Ticket, TicketCreateRequest, TicketStatusHistory
from app.schemas.ticket import TicketCreate
from app.security import Operator
from app.services.ticket import create_ticket


class TicketIdempotencyMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_survives_mcp_identity_check_and_http_header(self):
        from app.mcp_server import create_ticket as tool_create, _request
        with patch.dict(os.environ, {'MERIDIAN_EMPLOYEE_KEY':'fixture-jwt'}), patch('app.mcp_server._request', new_callable=AsyncMock) as request:
            request.side_effect = [{'role':'employee', 'employee_id':32}, {'id':123}]
            self.assertEqual(await tool_create('Wi-Fi', 'Fails', idempotency_key='stable-key'), {'id':123})
            self.assertEqual(request.call_args.kwargs['idempotency_key'], 'stable-key')
            self.assertEqual(request.call_args.kwargs['body']['employee_id'], 32)
        client = AsyncMock()
        client.request.return_value = httpx.Response(201, json={'id':123})
        with patch.dict(os.environ, {'MERIDIAN_EMPLOYEE_KEY':'fixture-jwt'}), patch('app.mcp_server.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            await _request('POST', '/tickets', body={'title':'Wi-Fi'}, idempotency_key='stable-key')
            self.assertEqual(factory.call_args.kwargs['headers']['Idempotency-Key'], 'stable-key')
            self.assertEqual(factory.call_args.kwargs['headers']['Authorization'], 'Bearer fixture-jwt')


class TicketIdempotencyApiTests(unittest.TestCase):
    setUp = test_auth.AuthenticationTests.setUp
    tearDown = test_auth.AuthenticationTests.tearDown
    account = test_auth.AuthenticationTests.account
    login = test_auth.AuthenticationTests.login
    headers = test_auth.AuthenticationTests.headers

    def payload(self, **changes):
        return {'title': 'Cannot connect', 'description': 'Office Wi-Fi fails', 'employee_id': self.owner['employee_id'], **changes}

    def create(self, key, payload=None, tokens=None):
        return self.client.post('/tickets', json=payload or self.payload(), headers={**self.headers(tokens or self.login()), 'Idempotency-Key': key})

    def test_replay_after_new_login_creates_one_ticket_and_one_history_event(self):
        key = uuid4().hex
        first = self.create(key)
        self.assertEqual(first.status_code, 201, first.text)
        replay = self.create(key)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(first.json(), replay.json())
        events = self.connection.scalar(select(func.count()).select_from(TicketStatusHistory).where(TicketStatusHistory.ticket_id == first.json()['id']))
        self.assertEqual(events, 1)
        reservation = self.connection.execute(select(TicketCreateRequest.__table__).where(TicketCreateRequest.actor_scope == f"employee:user:{self.owner['user_id']}")).mappings().one()
        self.assertNotEqual(reservation['key_hash'], key)
        self.assertEqual(reservation['ticket_id'], first.json()['id'])

    def test_same_key_changed_details_conflicts_but_new_key_allows_new_ticket(self):
        key = uuid4().hex
        first = self.create(key)
        conflict = self.create(key, self.payload(description='Different issue'))
        self.assertEqual(conflict.status_code, 409, conflict.text)
        second = self.create(uuid4().hex)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first.json()['id'], second.json()['id'])

    def test_key_is_scoped_to_authenticated_user_and_cannot_spoof_reporter(self):
        key = uuid4().hex
        first = self.create(key)
        other = self.login(self.other)
        second = self.create(key, self.payload(employee_id=self.other['employee_id']), other)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first.json()['id'], second.json()['id'])
        denied = self.create(key, self.payload(), other)
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_failed_transaction_does_not_reserve_key_or_leave_ticket(self):
        key = uuid4().hex
        with patch('app.services.ticket._save', side_effect=RuntimeError('Injected before commit')):
            with self.assertRaises(RuntimeError):
                self.create(key)
        self.assertEqual(self.connection.scalar(select(func.count()).select_from(TicketCreateRequest).where(TicketCreateRequest.actor_scope == f"employee:user:{self.owner['user_id']}")), 0)
        self.assertEqual(self.connection.scalar(select(func.count()).select_from(Ticket).where(Ticket.employee_id == self.owner['employee_id'])), 0)
        self.assertEqual(self.create(key).status_code, 201)

    def test_deleted_ticket_tombstone_blocks_recreation(self):
        key = uuid4().hex
        first = self.create(key)
        self.assertEqual(self.client.delete(f"/tickets/{first.json()['id']}", headers=self.admin).status_code, 204)
        self.assertEqual(self.create(key).status_code, 409)

    def test_reassignment_does_not_leak_ticket_on_replay(self):
        key = uuid4().hex
        first = self.create(key)
        response = self.client.patch(f"/tickets/{first.json()['id']}", json={'employee_id': self.other['employee_id']}, headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.create(key)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Office Wi-Fi', response.text)

    def test_invalid_keys_are_rejected_before_creation(self):
        for key in ('', 'has spaces', 'x' * 129):
            self.assertEqual(self.create(key).status_code, 422)


class TicketIdempotencyConcurrencyTests(unittest.TestCase):
    def test_independent_sessions_race_and_post_commit_retry_return_one_ticket(self):
        # Unlike API tests, this fixture must commit so both clients can see it.
        key = uuid4().hex
        with Session(engine) as db:
            employee = Employee(full_name='Idempotency race fixture', email=f'idempotency-{key}@example.com')
            db.add(employee)
            db.commit()
            employee_id = employee.id
        try:
            data = TicketCreate(title='Concurrent fixture', description='Generated race test', employee_id=employee_id)
            operator = Operator('employee', employee_id)
            barrier = Barrier(2)
            def attempt():
                with Session(engine) as db:
                    db.execute(text("SET LOCAL statement_timeout = '10s'"))
                    barrier.wait(timeout=10)
                    return create_ticket(db, data, operator, key).id
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(attempt) for _ in range(2)]
                ids = [future.result(timeout=20) for future in futures]
            self.assertEqual(ids[0], ids[1])
            with Session(engine) as db:
                self.assertEqual(create_ticket(db, data, operator, key).id, ids[0])
                self.assertEqual(db.scalar(select(func.count()).select_from(Ticket).where(Ticket.employee_id == employee_id)), 1)
                self.assertEqual(db.scalar(select(func.count()).select_from(TicketStatusHistory).where(TicketStatusHistory.ticket_id == ids[0])), 1)
        finally:
            with Session(engine) as db:
                db.execute(delete(TicketCreateRequest).where(TicketCreateRequest.actor_scope == f'employee:employee:{employee_id}'))
                db.execute(delete(Ticket).where(Ticket.employee_id == employee_id))
                db.execute(delete(Employee).where(Employee.id == employee_id))
                db.commit()
