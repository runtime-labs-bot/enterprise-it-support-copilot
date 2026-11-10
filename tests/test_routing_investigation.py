"""Controlled routing boundaries; not replays of lost historical model outputs."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.agent import retrieval_grader, question_classifier, web_result_grader
from app.evaluation.knowledge_worker import run
from app.evaluation.scorecard import catalog, fingerprint
from app.ingestion import chunk_documents
from app.services import answer_generator, web_answer_generator

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL_HASHES={
    'tc-014':'183573c54df91dbb605d117692ec773474346d91a03c58b75d36993618d41a67',
    'tc-043':'b3cfe17ff6eb508ffb713ce04344207f58efc5572ffecaa99e0684f11a6dd779',
}


def response(content):
    return SimpleNamespace(model='offline-routing-fixture',usage=None,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content),finish_reason='stop')])


class RoutingInvestigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={c['id']:c for c in catalog() if c['id'] in ORIGINAL_HASHES}
        with patch.object(chunk_documents,'KNOWLEDGE_BASE_DIR',ROOT/'data/knowledge_base'), redirect_stdout(io.StringIO()):
            chunks=chunk_documents.load_and_chunk_documents()
        vpn=[{**c,'id':c['chunk_id']} for c in chunks if c['document_id']=='vpn_troubleshooting']
        cls.internet=next(c for c in vpn if 'the problem is your local network, not the VPN' in c['text'])
        cls.port=next(c for c in vpn if 'TCP and UDP 443 outbound' in c['text'])
        cls.no_port=next(c for c in vpn if '443' not in c['text'] and c['chunk_number']==0)

    def trace(self,name,chunk,relevant,category='general_technical'):
        answer=('The managed VPN uses TCP and UDP 443 outbound. [Source 1]'
            if name=='tc-043' else 'Check whether a public site loads to test local internet access. [Source 1]')
        internal_grade=response(json.dumps({'relevant':relevant,'reason':'Controlled fixture decision.','missing_information':''}))
        classifier=response(json.dumps({'category':category,'reason':'Controlled fixture classification.'}))
        web_grade=response(json.dumps({'relevant':True,'reason':'Controlled public context.','missing_information':''}))
        public=[{'title':'Controlled networking reference','url':'https://vendor.example/networking','content':'Fixture supports outbound TCP and UDP 443 and local internet checks.'}]
        search=Mock(return_value=[chunk])
        with patch.dict('sys.modules',{'app.retrieval.search_knowledge':SimpleNamespace(search_knowledge=search)}), \
             patch.object(retrieval_grader.client.chat.completions,'create',return_value=internal_grade) as grade, \
             patch.object(question_classifier.client.chat.completions,'create',return_value=classifier) as classify, \
             patch.object(answer_generator.client.chat.completions,'create',return_value=response(answer)) as internal, \
             patch('app.agent.graph.search_web',return_value=public) as web_search, \
             patch.object(web_result_grader.client.chat.completions,'create',return_value=web_grade), \
             patch.object(web_answer_generator.client.chat.completions,'create',return_value=response(answer)) as web, \
             patch('socket.socket.connect',side_effect=AssertionError('External networking forbidden')):
            result=run(self.cases[name])
            if relevant:
                internal.assert_called_once();classify.assert_not_called();web_search.assert_not_called();web.assert_not_called()
            else:
                classify.assert_called_once();internal.assert_not_called()
                if category=='general_technical':web.assert_called_once();web_search.assert_called_once()
                else:web.assert_not_called();web_search.assert_not_called()
            prompt=grade.call_args.kwargs['messages'][1]['content']
            self.assertIn(self.cases[name]['question'],prompt)
            self.assertIn(chunk['text'],prompt)
            if relevant:
                self.assertIn(chunk['text'],internal.call_args.kwargs['messages'][1]['content'])
        self.assertNotIn(chunk['text'],json.dumps(result))
        self.assertNotIn(answer,json.dumps(result))
        return result

    def test_original_case_expectation_hashes_are_unchanged(self):
        for name,case in self.cases.items():
            self.assertEqual(fingerprint(case),ORIGINAL_HASHES[name])

    def test_014_relevant_internal_guidance_skips_classifier_but_fails_strict_web_route(self):
        result=self.trace('tc-014',self.internet,True)
        self.assertEqual(result['observations']['actual_status'],'answered')
        self.assertFalse(result['observations']['category_checked'])
        self.assertEqual([k for k,v in result['checks'].items() if not v],['status'])

    def test_014_public_route_passes_the_same_unchanged_case(self):
        result=self.trace('tc-014',self.internet,False)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['observations']['actual_status'],'answered_web')

    def test_043_supplied_port_fact_and_positive_grade_pass_unchanged_case(self):
        result=self.trace('tc-043',self.port,True)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['observations']['cited_document_ids'],['KB-NET-0042'])

    def test_043_rejected_fact_then_public_classification_recreates_saved_failure_checks(self):
        result=self.trace('tc-043',self.port,False)
        self.assertEqual(result['observations']['actual_status'],'answered_web')
        self.assertTrue(result['checks']['retrieved_expected_documents'])
        self.assertTrue(result['checks']['keyword:443'])
        self.assertEqual({k for k,v in result['checks'].items() if not v},{'status','category','expected_documents_actually_cited'})

    def test_043_document_recall_without_port_fact_does_not_certify_answerability(self):
        self.assertNotIn('443',self.no_port['text'])
        result=self.trace('tc-043',self.no_port,False,'internal_company')
        self.assertTrue(result['checks']['retrieved_expected_documents'])
        self.assertEqual(result['observations']['actual_status'],'insufficient_context')
        self.assertFalse(result['checks']['keyword:443'])
