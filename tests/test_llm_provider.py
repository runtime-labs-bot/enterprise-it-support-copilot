from contextlib import asynccontextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from dotenv import dotenv_values

from app.services.llm_provider import AsyncLLMClient, LLMClient, LLMConfig, LLMProviderError, get_config
from app.evaluation.knowledge_worker import run
from scripts.switch_llm import switch, main

SECRET = 'fixture-private-key'


def config(provider='groq'):
    values = {'LLM_PROVIDER':provider, 'LLM_MODEL':'fixture-model', 'GROQ_API_KEY':SECRET, 'OPENAI_API_KEY':SECRET, 'GEMINI_API_KEY':SECRET+'-gemini'}
    if provider == 'compatible':
        values.update(LLM_BASE_URL='https://compatible.example/v1',LLM_API_KEY=SECRET)
    return LLMConfig.from_values(values)


def response(content='Supported [Source 1].', tool_calls=None):
    return {'model':'fixture-model','choices':[{'message':{'role':'assistant','content':content,'tool_calls':tool_calls},'finish_reason':'tool_calls' if tool_calls else 'stop'}], 'usage':{'prompt_tokens':10,'completion_tokens':5,'completion_tokens_details':{'reasoning_tokens':0}}}


class ProviderConfigurationTests(unittest.TestCase):
    def test_explicit_evaluation_env_file_avoids_stale_local_selection(self):
        with TemporaryDirectory() as directory, patch('app.services.llm_provider.ROOT',Path(directory)):
            root=Path(directory)
            (root/'.env').write_text('LLM_PROVIDER=ollama\nLLM_MODEL=wrong-local-model\n')
            selected=root/'.env.docker'
            selected.write_text('LLM_PROVIDER=gemini\nLLM_MODEL=selected-fixture\nGEMINI_API_KEY=private-key\n')
            with patch.dict(os.environ,{'LLM_ENV_FILE':str(selected)},clear=True):
                actual=get_config()
            self.assertEqual((actual.provider,actual.model),('gemini','selected-fixture'))

    def test_legacy_groq_and_explicit_provider_selection_do_not_expose_keys(self):
        c = LLMConfig.from_values({'GROQ_API_KEY':SECRET,'GROQ_MODEL':'legacy-model'})
        self.assertEqual((c.provider,c.model),('groq','legacy-model'))
        self.assertNotIn(SECRET,repr(c))
        for provider in ('groq','openai','gemini','ollama','compatible'):
            self.assertEqual(config(provider).provider,provider)

    def test_cloud_credentials_cannot_be_sent_to_a_leftover_custom_endpoint(self):
        for provider in ('groq','openai','gemini'):
            with self.assertRaises(ValueError):
                LLMConfig.from_values({'LLM_PROVIDER':provider,'LLM_MODEL':'model','LLM_BASE_URL':'https://wrong.example/v1','GROQ_API_KEY':SECRET,'OPENAI_API_KEY':SECRET})
        with self.assertRaises(ValueError):
            LLMConfig.from_values({'LLM_PROVIDER':'compatible','LLM_MODEL':'model','LLM_BASE_URL':'https://custom.example/v1','OPENAI_API_KEY':SECRET})

    def test_invalid_configuration_fails_before_a_network_call(self):
        for values in ({'LLM_PROVIDER':'unknown'}, {'LLM_PROVIDER':'openai','OPENAI_API_KEY':SECRET}, {'LLM_PROVIDER':'openai','LLM_MODEL':'model'}, {'LLM_PROVIDER':'ollama','LLM_MODEL':'model','LLM_BASE_URL':'https://user:password@host/v1'}):
            with self.subTest(values=list(values)), self.assertRaises(ValueError):
                LLMConfig.from_values(values)

    def test_local_switch_overrides_stale_dotenv_selectors_without_changing_credentials(self):
        with TemporaryDirectory() as directory, patch('app.services.llm_provider.ROOT',Path(directory)), patch.dict(os.environ,{'LLM_PROVIDER':'groq','LLM_MODEL':'stale','GROQ_API_KEY':SECRET},clear=True):
            p=Path(directory)/'.env'
            p.write_text('LLM_PROVIDER=ollama\nLLM_MODEL=local-a\n')
            self.assertEqual(get_config().provider,'ollama')
            p.write_text('LLM_PROVIDER=ollama\nLLM_MODEL=local-b\n')
            self.assertEqual(get_config().model,'local-b')


class ProviderProtocolTests(unittest.TestCase):
    def test_read_timeout_is_distinct_from_the_outer_case_deadline_without_network(self):
        from app.evaluation.scorecard import run_knowledge
        original=httpx.Client
        captured={}
        def handle(request):
            captured['timeouts']=request.extensions['timeout']
            raise httpx.ReadTimeout('private transport detail '+SECRET,request=request)
        def client(**kwargs):
            return original(transport=httpx.MockTransport(handle),**kwargs)
        with patch('app.services.llm_provider.get_config',return_value=replace(config('gemini'),timeout=90)), patch('app.services.llm_provider.httpx.Client',side_effect=client), patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            with self.assertRaises(LLMProviderError) as caught:
                LLMClient().chat.completions.create(messages=[{'role':'user','content':'Offline fixture'}],max_tokens=10)
        self.assertEqual(captured['timeouts'],{'connect':90,'read':90,'write':90,'pool':90})
        self.assertEqual(caught.exception.error_kind,'transport')
        self.assertEqual(caught.exception.transport_error,'ReadTimeout')
        self.assertIsNone(caught.exception.status_code)
        with patch('app.agent.graph.workflow.compile',side_effect=caught.exception):
            outcome=run({'question':'Offline fixture'})
        self.assertFalse(outcome['provider_limited'])
        self.assertEqual(outcome['transport_error'],'ReadTimeout')
        self.assertNotIn(SECRET,json.dumps(outcome))
        case={'id':'offline-fixture','profile':'knowledge','group':'policy_citations','critical':False,'expected_status':'answered'}
        with patch('app.evaluation.scorecard.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(outcome))) as worker, redirect_stdout(io.StringIO()):
            results=run_knowledge([case],timeout=300)
        self.assertEqual(worker.call_args.kwargs['timeout'],300)
        self.assertEqual(results[0]['error_type'],'LLMProviderError')
        self.assertEqual(results[0]['transport_error'],'ReadTimeout')
        self.assertNotIn('http_status',results[0])

    def test_gemini_normalized_answers_still_pass_through_the_citation_guard(self):
        from app.agent.graph import generate_response
        original=httpx.Client
        for candidate, expected in (('The pass lasts 8 hours [Source 1].','answered'),('The pass lasts 8 hours.','insufficient_context')):
            def handle(request):
                return httpx.Response(200,json=response(candidate))
            with patch('app.services.llm_provider.get_config',return_value=config('gemini')), patch('app.services.llm_provider.httpx.Client',side_effect=lambda **kw: original(transport=httpx.MockTransport(handle),**kw)), redirect_stdout(io.StringIO()):
                result=generate_response({'question':'How long?', 'retrieved_chunks':[{'id':'fixture','source':'fixture.md','text':'A pass lasts 8 hours.'}]})
            self.assertEqual(result['status'],expected)
            self.assertNotIn(SECRET,json.dumps(result))
            if expected=='insufficient_context':
                self.assertEqual(result['sources'],[])

    def test_sync_profiles_preserve_json_mode_and_map_provider_parameters(self):
        original = httpx.Client
        for provider in ('groq','openai','gemini','ollama','compatible'):
            requests=[]
            def handle(request):
                requests.append(request)
                return httpx.Response(200,json=response('{"relevant":true}'))
            def client(**kwargs):
                return original(transport=httpx.MockTransport(handle),**kwargs)
            with self.subTest(provider=provider), patch('app.services.llm_provider.get_config',return_value=config(provider)), patch('app.services.llm_provider.httpx.Client',side_effect=client):
                result = LLMClient().chat.completions.create(messages=[{'role':'user','content':'Return JSON'}],max_tokens=800,temperature=0,response_format={'type':'json_object'})
            payload=json.loads(requests[0].content)
            self.assertEqual(payload['model'],'fixture-model')
            self.assertEqual(payload['response_format'],{'type':'json_object'})
            self.assertEqual(payload[config(provider).token_parameter],800)
            self.assertEqual('temperature' in payload,provider != 'openai')
            self.assertEqual(result.choices[0].message.content,'{"relevant":true}')
            self.assertEqual(result.usage.completion_tokens,5)
            self.assertEqual(len(requests),1)
            if provider == 'gemini':
                self.assertEqual(str(requests[0].url),'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions')
                self.assertEqual(requests[0].headers['Authorization'],'Bearer '+SECRET+'-gemini')

    def test_quota_error_preserves_reset_headers_without_body_or_credentials_or_retry(self):
        original=httpx.Client
        requests=[]
        def handle(request):
            requests.append(request)
            return httpx.Response(429,text='private provider response '+SECRET,headers={'retry-after':'60','x-ratelimit-reset-tokens':'1m','authorization':SECRET})
        with patch('app.services.llm_provider.get_config',return_value=config()), patch('app.services.llm_provider.httpx.Client',side_effect=lambda **kw: original(transport=httpx.MockTransport(handle),**kw)):
            with self.assertRaises(LLMProviderError) as caught:
                LLMClient().chat.completions.create(messages=[],max_tokens=10)
        self.assertEqual(caught.exception.status_code,429)
        self.assertEqual(caught.exception.reset_headers,{'retry-after':'60','x-ratelimit-reset-tokens':'1m'})
        self.assertNotIn(SECRET,str(caught.exception))
        self.assertEqual(len(requests),1)
        with patch('app.agent.graph.workflow.compile',side_effect=caught.exception):
            result=run({'question':'Fixture'})
        self.assertTrue(result['provider_limited'])
        self.assertEqual(result['rate_limit_headers']['retry-after'],'60')

    def test_malformed_response_and_network_failure_are_sanitized(self):
        original=httpx.Client
        for mode in ('invalid','network'):
            def handle(request):
                if mode=='network':
                    raise httpx.ConnectError(SECRET,request=request)
                return httpx.Response(200,json={'private':SECRET})
            with patch('app.services.llm_provider.get_config',return_value=config()), patch('app.services.llm_provider.httpx.Client',side_effect=lambda **kw: original(transport=httpx.MockTransport(handle),**kw)):
                with self.assertRaises(LLMProviderError) as caught:
                    LLMClient().chat.completions.create(messages=[])
                self.assertNotIn(SECRET,str(caught.exception))
                self.assertEqual(caught.exception.error_kind,'transport' if mode=='network' else 'invalid_response')
                if mode=='network':
                    self.assertEqual(caught.exception.transport_error,'ConnectError')


class AsyncProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_preserves_signatures_across_sequential_tool_calls(self):
        from app.agent.meridian import _run
        from test_meridian import FakeSession
        original=httpx.AsyncClient
        requests=[]
        session=FakeSession()
        @asynccontextmanager
        async def connect(*args):
            yield session
        def handle(request):
            requests.append(json.loads(request.content))
            step=len(requests)
            calls=None
            if step <= 2:
                calls=[{'id':f'call-{step}','type':'function','function':{'name':'get_current_employee' if step==1 else 'list_tickets','arguments':'{}'},'extra_content':{'google':{'thought_signature':f'opaque-signature-{step}'}}}]
            return httpx.Response(200,json=response(None if calls else 'Done',calls))
        with patch('app.services.llm_provider.get_config',return_value=config('gemini')), patch('app.services.llm_provider.httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(handle),**kw)), patch('app.agent.meridian.connect_meridian',connect):
            result=await _run('Show my tickets','',employee_api_key='employee-fixture',operator_role='employee')
        assistants=[m for m in requests[2]['messages'] if m['role']=='assistant']
        self.assertEqual([m['tool_calls'][0]['extra_content']['google']['thought_signature'] for m in assistants],['opaque-signature-1','opaque-signature-2'])
        self.assertEqual(session.calls,[('get_current_employee',{}),('list_tickets',{})])
        self.assertNotIn('opaque-signature',json.dumps(result))

    async def test_async_mcp_loop_uses_the_same_provider_and_replays_tool_messages(self):
        from app.agent.meridian import _run
        from test_meridian import FakeSession
        original=httpx.AsyncClient
        for provider in ('groq','openai','gemini','ollama','compatible'):
            requests=[]
            session=FakeSession()
            @asynccontextmanager
            async def connect(*args):
                yield session
            def handle(request):
                requests.append(json.loads(request.content))
                calls=[{'id':'lookup','type':'function','function':{'name':'get_current_employee','arguments':'{}'}}] if len(requests)==1 else None
                payload=response(None if calls else 'Found',calls)
                if calls:
                    payload['choices'][0]['message'].pop('content')
                    if provider == 'gemini':
                        calls[0]['extra_content']={'google':{'thought_signature':'opaque-fixture-signature'}}
                return httpx.Response(200,json=payload)
            with patch('app.services.llm_provider.get_config',return_value=config(provider)), patch('app.services.llm_provider.httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(handle),**kw)), patch('app.agent.meridian.connect_meridian',connect):
                result=await _run('Show my record','',employee_api_key='private-employee-token',operator_role='employee')
            self.assertEqual(result['answer'],'Found')
            self.assertEqual(session.calls,[('get_current_employee',{})])
            self.assertEqual(requests[0]['tool_choice'],'auto')
            self.assertEqual(requests[1]['messages'][-1]['role'],'tool')
            self.assertNotIn('private-employee-token',json.dumps(requests))
            if provider == 'gemini':
                assistant=next(m for m in requests[1]['messages'] if m['role']=='assistant')
                self.assertEqual(assistant['tool_calls'][0]['extra_content']['google']['thought_signature'],'opaque-fixture-signature')
                self.assertNotIn('opaque-fixture-signature',json.dumps(result))


class SwitchCommandTests(unittest.TestCase):
    def test_gemini_switch_requires_its_own_key_and_preserves_other_credentials(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env'
            path.write_text('GROQ_API_KEY='+SECRET+'\nOPENAI_API_KEY=other-fixture\n')
            original=path.read_bytes()
            with self.assertRaises(ValueError):
                switch(path,'gemini','gemini-fixture')
            self.assertEqual(path.read_bytes(),original)
            with path.open('a') as stream:
                stream.write('GEMINI_API_KEY=gemini-fixture-key\n')
            selected=switch(path,'gemini','gemini-fixture')
            self.assertEqual(selected.key_variable,'GEMINI_API_KEY')
            values=dotenv_values(path)
            self.assertEqual(values['GROQ_API_KEY'],SECRET)
            self.assertEqual(values['GEMINI_API_KEY'],'gemini-fixture-key')
            self.assertEqual(values['LLM_PROVIDER'],'gemini')

    def test_missing_docker_executable_returns_failure_without_key_output(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env.docker'
            path.write_text('GROQ_API_KEY='+SECRET+'\n')
            output=io.StringIO()
            with patch('sys.argv',['switch_llm','groq','--docker','--env-file',str(path)]), redirect_stdout(output), patch('scripts.switch_llm.subprocess.run',side_effect=FileNotFoundError(SECRET)):
                self.assertEqual(main(),1)
            self.assertNotIn(SECRET,output.getvalue())

    def test_atomic_switch_preserves_secrets_and_unrelated_configuration(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env'
            path.write_text('OPENAI_API_KEY='+SECRET+'\nGROQ_API_KEY=old-groq\nDB_PASSWORD=untouched\n')
            switch(path,'openai','selected-model')
            values=dotenv_values(path)
            self.assertEqual(values['OPENAI_API_KEY'],SECRET)
            self.assertEqual(values['DB_PASSWORD'],'untouched')
            self.assertEqual(values['LLM_PROVIDER'],'openai')
            original=path.read_bytes()
            with self.assertRaises(ValueError):
                switch(path,'compatible','model','https://custom.example/v1')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(directory).glob('.env.switch-*')),[])

    def test_cli_status_never_prints_key_or_calls_provider(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env'
            path.write_text('GROQ_API_KEY='+SECRET+'\n')
            output=io.StringIO()
            with patch('sys.argv',['switch_llm','--show','--env-file',str(path)]), redirect_stdout(output), patch('httpx.Client') as network:
                self.assertEqual(main(),0)
            network.assert_not_called()
            self.assertNotIn(SECRET,output.getvalue())

    def test_docker_switch_targets_copilot_and_uses_host_ollama_address(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env.docker'
            path.write_text('DOCKER_DB_PASSWORD=fixture-db\n')
            with patch('sys.argv',['switch_llm','ollama','--model','local-model','--docker','--env-file',str(path)]), redirect_stdout(io.StringIO()), patch('scripts.switch_llm.subprocess.run') as docker:
                docker.return_value.returncode=0
                self.assertEqual(main(),0)
            args=docker.call_args.args[0]
            self.assertEqual(args[-2:],['--no-deps','copilot'])
            self.assertEqual(dotenv_values(path)['LLM_BASE_URL'],'http://host.docker.internal:11434/v1')


class ProviderReportTests(unittest.TestCase):
    def test_invalid_selection_does_not_destroy_an_error_report(self):
        from app.evaluation.scorecard import finish, row
        case={'id':'fixture','profile':'knowledge','group':'policy_citations','critical':False,'expected_status':'answered'}
        with TemporaryDirectory() as directory:
            args=SimpleNamespace(fail_under=1,merge=None,profile='knowledge',limit=1,timeout=120,output=Path(directory)/'report')
            with patch('app.services.llm_provider.get_config',side_effect=ValueError('Invalid')), redirect_stdout(io.StringIO()):
                self.assertEqual(finish([row(case,{'status':'error','error_type':'ValueError'})],args,None),1)
            data=json.loads(args.output.with_suffix('.json').read_text())
            self.assertEqual(data['provenance']['provider'],'unconfigured')
            self.assertEqual(data['summary']['errors'],1)
