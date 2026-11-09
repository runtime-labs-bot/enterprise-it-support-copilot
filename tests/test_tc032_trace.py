"""Controlled pipeline reproduction, not a replay of the lost live response."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.agent import retrieval_grader
from app.evaluation.knowledge_worker import run
from app.ingestion import chunk_documents
from app.services import answer_generator

ROOT = Path(__file__).resolve().parents[1]


class TemporaryAccessPassTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = next(case for case in json.loads((ROOT/'evals/test_cases.json').read_text()) if case['id'] == 'tc-032')
        with patch.object(chunk_documents, 'KNOWLEDGE_BASE_DIR', ROOT/'data/knowledge_base'), redirect_stdout(io.StringIO()):
            chunks = chunk_documents.load_and_chunk_documents()
        local = next(chunk for chunk in chunks if chunk['document_id'] == 'mfa_enrollment_and_recovery' and 'A single-use code valid for 8 hours.' in chunk['text'])
        cls.chunk = {**local, 'id': local['chunk_id']}

    def trace(self, candidate, finish='stop'):
        grader = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'relevant':True, 'reason':'The supplied section gives the TAP lifetime.', 'missing_information':''})))])
        response = SimpleNamespace(model='offline-fixture', usage=SimpleNamespace(prompt_tokens=100, completion_tokens=800 if finish == 'length' else 30, completion_tokens_details=SimpleNamespace(reasoning_tokens=790 if finish == 'length' else 0)), choices=[SimpleNamespace(message=SimpleNamespace(content=candidate), finish_reason=finish)])
        search = Mock(return_value=[self.chunk])
        # Import interception prevents Pinecone client/index initialization as well
        # as search requests. The network tripwire also guards the model boundaries.
        with patch.dict('sys.modules', {'app.retrieval.search_knowledge':SimpleNamespace(search_knowledge=search)}), patch.object(retrieval_grader.client.chat.completions,'create',return_value=grader) as grade, patch.object(answer_generator.client.chat.completions,'create',return_value=response) as generate, patch('socket.socket.connect',side_effect=AssertionError('Network forbidden in offline trace')):
            result = run(self.case)
            search.assert_called_once()
            grade.assert_called_once()
            generate.assert_called_once()
            for call in (grade.call_args, generate.call_args):
                prompt = call.kwargs['messages'][1]['content']
                self.assertIn(self.case['question'], prompt)
                self.assertIn('A single-use code valid for 8 hours.', prompt)
        self.assertNotIn('A single-use code valid for 8 hours.', json.dumps(result))
        self.assertNotIn(candidate, json.dumps(result))
        return result

    def test_correct_fact_disappears_at_guard_when_model_omits_citation(self):
        result = self.trace('A Temporary Access Pass is valid for 8 hours and can be used once.')
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['checks']['retrieved_expected_documents'])
        self.assertFalse(result['checks']['keyword:8'])
        trace = result['observations']['pipeline']
        self.assertTrue(trace['retrieval_relevant'])
        self.assertEqual(trace['generation']['source_kind'], 'internal')
        self.assertEqual(trace['generation']['validation']['rejection_reasons'], ['missing_citation_labels'])
        self.assertTrue(trace['generation']['literal_expected_keyword_presence']['8'])
        self.assertEqual(result['observations']['actual_status'], 'insufficient_context')

    def test_truncated_generation_is_distinguished_from_missing_citation(self):
        result = self.trace('A Temporary Access Pass is valid for 8 hours and single-use [Source 1].', 'length')
        generation = result['observations']['pipeline']['generation']
        self.assertEqual(generation['validation']['rejection_reasons'], ['incomplete_generation'])
        self.assertEqual(generation['validation']['referenced_source_ids'], [1])
        self.assertEqual(generation['finish_reason'], 'length')
        self.assertEqual(generation['completion_tokens'], 800)
        self.assertEqual(generation['requested_max_tokens'], 800)
        self.assertEqual(generation['reasoning_tokens'], 790)
        self.assertTrue(generation['literal_expected_keyword_presence']['8'])
        self.assertEqual(result['observations']['actual_status'], 'insufficient_context')

    def test_complete_correct_cited_answer_passes_with_unchanged_case_expectations(self):
        for label in ('[Source 1]', '\u3010Source 1\u3011'):
            with self.subTest(label=label):
                result = self.trace('A Temporary Access Pass is valid for 8 hours and single-use ' + label + '.')
                self.assertEqual(result['status'], 'passed')
                self.assertTrue(all(result['checks'].values()))
                generation = result['observations']['pipeline']['generation']
                self.assertTrue(generation['validation']['accepted'])
                self.assertEqual(generation['validation']['rejection_reasons'], [])
