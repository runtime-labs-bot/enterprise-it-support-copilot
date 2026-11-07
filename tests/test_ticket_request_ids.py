"""Trusted request IDs survive retries without accepting model-supplied keys."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.api.main import app
from app.agent.meridian import _tool_definitions, run_tool_loop
from app.services.admin_actions import AdminActionStore
from test_meridian import FakeSession, tool_call
from test_meridian_api_ui import tokens


class RequestIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_reuses_trusted_key_but_new_request_uses_new_key(self):
        sessions = []
        for key in ('request-one', 'request-one', 'request-two'):
            session = FakeSession()
            model = AsyncMock(side_effect=[tool_call('create_ticket', {'employee_id':32, 'idempotency_key':'model-forged'}), {'content':'Done'}])
            await run_tool_loop(session, model, 'Create a ticket', '', request_id=key)
            sessions.append(session)
            self.assertEqual(session.calls[0][1]['idempotency_key'], key)
        self.assertEqual(sessions[0].calls, sessions[1].calls)
        self.assertNotEqual(sessions[0].calls, sessions[2].calls)

    async def test_model_schema_hides_reserved_key_without_mutating_mcp_schema(self):
        schema = {'type':'object', 'properties':{'title':{'type':'string'},'idempotency_key':{'type':'string'}}, 'required':['title']}
        tool = SimpleNamespace(name='create_ticket', description='', inputSchema=schema)
        result = _tool_definitions([tool])
        self.assertNotIn('idempotency_key', json.dumps(result))
        self.assertIn('idempotency_key', schema['properties'])


class RequestBoundaryTests(unittest.TestCase):
    def test_api_retries_have_same_message_id_and_separate_threads_have_different_ids(self):
        answer = {'answer':'Fixture', 'status':'answered_meridian'}
        with patch('app.api.main.backend_request', return_value=tokens()['user']), patch('app.api.main.history.is_archived', return_value=False), patch('app.api.main.agent.invoke', return_value=answer) as invoke, TestClient(app) as client:
            ids = []
            for thread, request_id in (('one','request-one'),('one','request-one'),('two','request-one'),('one:two','three'),('one','two:three')):
                response = client.post('/ask', json={'question':'Create a ticket', 'thread_id':thread, 'request_id':request_id}, headers={'Authorization':'Bearer fixture'})
                self.assertEqual(response.status_code, 200, response.text)
                ids.append(invoke.call_args.args[0]['messages'][0].id)
            self.assertEqual(ids[0], ids[1])
            self.assertNotEqual(ids[0], ids[2])
            self.assertNotEqual(ids[3], ids[4])

    def test_confirmed_admin_ticket_uses_persisted_action_id_as_backend_key(self):
        with TemporaryDirectory() as directory:
            store = AdminActionStore(Path(directory) / 'actions.sqlite')
            plan = {'operation':'create_ticket', 'changes':{'title':'Wi-Fi', 'description':'Fails', 'employee_id':32}}
            action = store.propose('user:1', 'thread', plan, 'Bearer fixture')
            with patch('app.services.admin_actions.backend_request', return_value={'id':123}) as request:
                store.confirm('user:1', 'thread', action['id'], 'Bearer fixture')
            self.assertEqual(request.call_args.kwargs['idempotency_key'], action['id'])
