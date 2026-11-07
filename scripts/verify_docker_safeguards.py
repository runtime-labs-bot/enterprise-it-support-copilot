"""Verify deployed ticket idempotency and citation guards without provider calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import subprocess
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def compose(service, code, stdin=''):
    result = subprocess.run(['docker','compose','--env-file','.env.docker','exec','-T',service,'python','-c',code], input=stdin, cwd=ROOT, text=True, capture_output=True, timeout=60)
    require(result.returncode == 0, f'{service} container verification failed ({result.returncode})')
    return result.stdout.strip()


def main():
    config = {**dotenv_values(ROOT / '.env.docker', interpolate=False), **os.environ}
    base = 'http://127.0.0.1:' + config.get('MERIDIAN_PORT','8000')
    admin = {'X-API-Key':config['DOCKER_ADMIN_API_KEY']}
    employees, users = [], []
    evidence = {}
    with httpx.Client(base_url=base, timeout=20, trust_env=False, follow_redirects=False) as client:
        try:
            identities = []
            for _ in range(2):
                email = f'docker-idempotency-{uuid4().hex}@example.com'
                password = secrets.token_urlsafe(24)
                result = client.post('/employees', headers=admin, json={'full_name':'Disposable Docker verification','email':email})
                require(result.status_code == 201, 'Create employee fixture')
                employee_id = result.json()['id']
                employees.append(employee_id)
                result = client.post('/auth/users', headers=admin, json={'employee_id':employee_id,'password':password,'role':'employee'})
                require(result.status_code == 201, 'Create login fixture')
                users.append(result.json()['id'])
                result = client.post('/auth/login', json={'email':email,'password':password})
                require(result.status_code == 200, 'Login fixture')
                identities.append({'Authorization':'Bearer ' + result.json()['access_token']})
            key = uuid4().hex
            payload = {'title':'Disposable Docker idempotency check','description':'Generated fixture; safe to remove','employee_id':employees[0]}
            headers = {**identities[0], 'Idempotency-Key':key}
            def send():
                return client.post('/tickets', headers=headers, json=payload)
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _:send(),range(2)))
            require(all(r.status_code == 201 for r in responses), 'Concurrent API creation')
            ticket_id = responses[0].json()['id']
            require(responses[1].json()['id'] == ticket_id, 'Concurrent replay returns original ticket')
            require(send().json()['id'] == ticket_id, 'Post-commit API replay')
            require(client.post('/tickets',headers=headers,json={**payload,'description':'Changed'}).status_code == 409, 'Changed payload conflicts')
            rows = client.get('/tickets',headers=identities[0]).json()
            require(len(rows) == 1 and rows[0]['id'] == ticket_id, 'Exactly one owned ticket')
            require(len(client.get(f'/tickets/{ticket_id}/history',headers=identities[0]).json()) == 1, 'Exactly one creation history event')
            require(client.get(f'/tickets/{ticket_id}',headers=identities[1]).status_code == 404, 'Other employee cannot read replayed ticket')
            other = client.post('/tickets',headers={**identities[1],'Idempotency-Key':key},json={**payload,'employee_id':employees[1]})
            require(other.status_code == 201 and other.json()['id'] != ticket_id, 'Same key remains isolated by user')
            evidence['deployed_http_idempotency'] = 'passed'
            evidence['deployed_employee_isolation'] = 'passed'
        finally:
            for employee_id in employees:
                result = client.get('/tickets',headers=admin,params={'employee_id':employee_id,'limit':100})
                require(result.status_code == 200, 'Discover owned fixture tickets for cleanup')
                for ticket in result.json():
                    require(client.delete(f"/tickets/{ticket['id']}",headers=admin).status_code == 204, 'Delete fixture ticket')
            if users:
                compose('meridian', "import json,sys; from sqlalchemy import delete; from app.database import SessionLocal; from app.models import TicketCreateRequest; scopes=['employee:user:'+str(i) for i in json.load(sys.stdin)]; db=SessionLocal(); db.execute(delete(TicketCreateRequest).where(TicketCreateRequest.actor_scope.in_(scopes))); db.commit(); db.close()", json.dumps(users))
            for employee_id in employees:
                require(client.delete(f'/employees/{employee_id}',headers=admin).status_code == 204, 'Delete fixture employee/account')
            evidence['fixture_cleanup'] = 'passed'
    guard_code = '''
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
import io, json
from app.services import answer_generator as internal, web_answer_generator as web
from app.agent.graph import generate_response, web_generate_node, conn
checks = 0
with redirect_stdout(io.StringIO()), patch('socket.socket.connect', side_effect=AssertionError('Provider network disabled')):
    for module, node, state in [(internal, generate_response, {'question':'Fixture?','retrieved_chunks':[{'id':'fixture','source':'fixture.md','text':'Fixture policy'}]}), (web, web_generate_node, {'question':'Fixture?','web_results':[{'url':'https://example.com/fixture','title':'Fixture','content':'Fixture instructions'}]})]:
        for answer, finish, expected in [('Uncited claim','stop','insufficient_context'), ('Claim [Source 99]','stop','insufficient_context'), ('Partial [Source 1]','length','insufficient_context'), ('Supported [Source 1]','stop',None), ('Supported '+chr(0x3010)+'Source 1'+chr(0x3011),'stop',None)]:
            response=SimpleNamespace(model='fixture',usage=None,choices=[SimpleNamespace(message=SimpleNamespace(content=answer),finish_reason=finish)])
            with patch.object(module.client.chat.completions,'create',return_value=response) as create:
                result=node(state)
                assert result['status'] == (expected or ('answered' if module is internal else 'answered_web'))
                if expected:
                    assert result['sources'] == [] and '?' in result['answer']
                else:
                    assert result['sources'] and result['answer'] == answer
                create.assert_called_once()
                checks += 1
conn.close()
print(json.dumps({'checks':checks,'provider_calls':0,'status':'passed'}))
'''
    evidence['deployed_citation_guard'] = json.loads(compose('copilot',guard_code))
    output=ROOT/'evals/reports/docker-safeguards.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,indent=2))


if __name__ == '__main__':
    main()
