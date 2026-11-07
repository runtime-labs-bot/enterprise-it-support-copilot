"""Failed citation output never becomes a successful sourced answer."""
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app.services import answer_generator, web_answer_generator
from app.agent.graph import generate_response, web_generate_node


class GeneratedCitationTests(unittest.TestCase):
    def response(self, answer, finish='stop'):
        return SimpleNamespace(model='fixture', usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason=finish)])

    def test_missing_fabricated_or_truncated_citations_fail_closed_without_retry(self):
        for module, function, inputs in (
            (answer_generator, answer_generator.generate_answer, [{'id':'chunk', 'source':'password_reset_and_unlock.md', 'text':'Password policy', 'section':'Policy'}]),
            (web_answer_generator, web_answer_generator.generate_web_answer, [{'title':'Vendor', 'url':'https://vendor.example/help', 'content':'Instructions'}]),
        ):
            for answer, finish in (('An unsupported answer.', 'stop'), ('Claim [Source 99].', 'stop'), ('Partial [Source 1]', 'length'), ('', 'stop'), (None, 'stop')):
                with self.subTest(module=module.__name__, answer=answer, finish=finish), patch.object(module.client.chat.completions, 'create', return_value=self.response(answer, finish)) as create, redirect_stdout(io.StringIO()):
                    result = function('Help?', inputs)
                    self.assertFalse(result['grounded'])
                    self.assertEqual(result['sources'], [])
                    self.assertIn('?', result['answer'])
                    self.assertNotEqual(result['answer'], answer)
                    create.assert_called_once()

    def test_both_supported_styles_keep_valid_source_metadata(self):
        for label in ('[Source 1]', '【Source 1】'):
            answer = 'Use the reset procedure ' + label
            with patch.object(answer_generator.client.chat.completions, 'create', return_value=self.response(answer)), redirect_stdout(io.StringIO()):
                result = answer_generator.generate_answer('Help?', [{'id':'chunk', 'source':'policy.md', 'text':'Reset procedure'}])
            self.assertEqual(result['answer'], answer)
            self.assertEqual(result['sources'][0]['chunk_id'], 'chunk')

    def test_graph_marks_failed_internal_and_web_generations_as_insufficient_context(self):
        result = {'answer':'Could you clarify?', 'sources':[], 'grounded':False}
        with patch('app.agent.graph.generate_answer', return_value=result), patch('app.agent.graph.generate_web_answer', return_value=result), redirect_stdout(io.StringIO()):
            self.assertEqual(generate_response({'question':'Help?', 'retrieved_chunks':[]})['status'], 'insufficient_context')
            self.assertEqual(web_generate_node({'question':'Help?', 'web_results':[]})['status'], 'insufficient_context')
