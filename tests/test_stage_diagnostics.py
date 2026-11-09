from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import httpx

from app.evaluation.knowledge_worker import run
from app.evaluation.readiness import check_readiness
from app.services.llm_provider import LLMConfig
from app.services.stage_diagnostics import capture_stages,stage,finalize_stages

PRIVATE='employee-private@example.invalid policy-content private-key'
CASE={'question':'How long is a pass valid?','expected_status':'answered','expected_category':'internal_company',
      'expected_document_ids':['KB-IAM-0015'],'expected_keywords':['8']}
CHUNK={'id':'fixture','document_id':'mfa_enrollment_and_recovery','source':'fixture.md','text':'Valid for 8 hours. '+PRIVATE}
CONFIG=LLMConfig.from_values({'LLM_PROVIDER':'gemini','LLM_MODEL':'fixture-model','GEMINI_API_KEY':'private-key'})


def completion(content):
    return {'model':'fixture-model','choices':[{'message':{'content':content},'finish_reason':'stop'}],'usage':{}}


class StageDiagnosticsTests(unittest.TestCase):
    def pipeline(self,fail_at=None,cited=True):
        original=httpx.Client
        calls=[]
        def handle(request):
            body=json.loads(request.content)
            grading='relevance grader' in body['messages'][0]['content']
            calls.append('relevance_grading' if grading else 'answer_generation')
            if fail_at==calls[-1]:
                raise httpx.ReadTimeout(PRIVATE,request=request)
            return httpx.Response(200,json=completion('{"relevant":true}' if grading else ('Valid for 8 hours [Source 1].' if cited else 'Valid for 8 hours.')))
        search=Mock(return_value=[CHUNK])
        if fail_at=='retrieval':
            search.side_effect=TimeoutError(PRIVATE)
        with patch.dict('sys.modules',{'app.retrieval.search_knowledge':SimpleNamespace(search_knowledge=search)}), patch('app.services.llm_provider.get_config',return_value=CONFIG), patch('app.services.llm_provider.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)), patch('socket.socket.connect',side_effect=AssertionError('External network forbidden')):
            result=run(CASE)
        self.assertNotIn(PRIVATE,json.dumps(result))
        self.assertNotIn('private-key',json.dumps(result))
        return result,calls

    def test_all_four_stages_and_retries_are_recorded_on_success(self):
        result,calls=self.pipeline()
        self.assertEqual(result['status'],'passed')
        stages=result['stage_diagnostics']
        self.assertEqual([s['stage'] for s in stages],['retrieval','relevance_grading','answer_generation','citation_safeguard'])
        self.assertTrue(all(s['status']=='completed' for s in stages))
        self.assertTrue(all(s['elapsed_seconds']>=0 for s in stages))
        self.assertEqual(stages[0]['provider'],'pinecone')
        self.assertIsNone(stages[0]['retry_count'])
        self.assertIsNone(stages[0]['model'])
        for item in stages[1:]:
            self.assertEqual((item['provider'],item['model'],item['retry_count']),('gemini','fixture-model',0))
        self.assertEqual(stages[1]['phase_timeouts_seconds']['read'],CONFIG.timeout)
        self.assertEqual(stages[-1]['execution'],'local_validation')
        self.assertIsNone(stages[-1]['timeout_seconds'])

    def test_retrieval_timeout_retains_failure_and_marks_other_stages_not_run(self):
        result,calls=self.pipeline('retrieval')
        self.assertEqual(calls,[])
        stages=result['stage_diagnostics']
        self.assertEqual(stages[0]['stage'],'retrieval')
        self.assertEqual(stages[0]['timeout_category'],'unspecified')
        self.assertTrue(all(s['status']=='not_run' for s in stages[1:]))

    def test_grading_timeout_is_attributed_before_generation(self):
        result,calls=self.pipeline('relevance_grading')
        self.assertEqual(calls,['relevance_grading'])
        stages=result['stage_diagnostics']
        self.assertEqual(stages[0]['status'],'completed')
        self.assertEqual(stages[1]['timeout_category'],'read')
        self.assertEqual(stages[1]['request_count'],1)
        self.assertTrue(all(s['status']=='not_run' for s in stages[2:]))

    def test_generation_timeout_preserves_successful_retrieval_and_grade(self):
        result,calls=self.pipeline('answer_generation')
        stages=result['stage_diagnostics']
        self.assertEqual([s['status'] for s in stages],['completed','completed','error','not_run'])
        self.assertEqual(stages[2]['timeout_category'],'read')

    def test_citation_rejection_is_not_reported_as_timeout(self):
        result,calls=self.pipeline(cited=False)
        self.assertEqual(result['status'],'failed')
        guard=result['stage_diagnostics'][-1]
        self.assertEqual(guard['status'],'rejected')
        self.assertEqual(guard['rejection_reasons'],['missing_citation_labels'])
        self.assertIsNone(guard['timeout_category'])

    def test_capture_is_opt_in_and_monotonic_elapsed_is_exact(self):
        with stage('retrieval') as event:
            self.assertIsNone(event)
        records=[]
        with capture_stages(records), patch('app.services.stage_diagnostics.time.perf_counter',side_effect=[10,11.25]):
            with stage('retrieval',provider='pinecone'):
                pass
        self.assertEqual(records[0]['elapsed_seconds'],1.25)
        self.assertIsNone(finalize_stages(records)[1]['elapsed_seconds'])

    def test_error_capture_does_not_leak_into_the_next_evaluation(self):
        first,second=[],[]
        with self.assertRaises(RuntimeError),capture_stages(first):
            with stage('retrieval',provider='pinecone'):
                raise RuntimeError(PRIVATE)
        with capture_stages(second):
            with stage('citation_safeguard',provider='local'):
                pass
        self.assertEqual([s['stage'] for s in first],['retrieval'])
        self.assertEqual([s['stage'] for s in second],['citation_safeguard'])
        self.assertNotIn(PRIVATE,json.dumps(first+second))


class ReadinessTests(unittest.TestCase):
    def probe(self,mode):
        original=httpx.Client
        requests=[]
        def handle(request):
            requests.append(request)
            if mode=='timeout':raise httpx.ReadTimeout(PRIVATE,request=request)
            if mode=='503':return httpx.Response(503,json={'error':PRIVATE})
            return httpx.Response(200,json=completion('{"ready":true}' if mode=='ready' else '{"ready":false}'))
        with patch('app.services.llm_provider.get_config',return_value=CONFIG), patch('app.evaluation.readiness.get_config',return_value=CONFIG), patch('app.services.llm_provider.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)), patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            result=check_readiness()
        self.assertEqual(len(requests),1)
        self.assertNotIn(PRIVATE,json.dumps(result))
        self.assertNotIn('private-key',json.dumps(result))
        return result

    def test_one_successful_request_confirms_readiness_without_retrieval(self):
        result=self.probe('ready')
        self.assertTrue(result['ready'])
        self.assertEqual(result['stage_diagnostics'][0]['component'],'readiness_json')
        self.assertEqual(result['stage_diagnostics'][0]['request_count'],1)

    def test_failure_stops_readiness_without_retry(self):
        for mode in ('timeout','503','invalid'):
            with self.subTest(mode=mode):
                self.assertFalse(self.probe(mode)['ready'])
