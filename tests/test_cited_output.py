from contextlib import redirect_stdout
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.cited_output import render_cited_output
from app.services import answer_generator, web_answer_generator
from app.evaluation.scoring import score_knowledge


class CitedOutputTests(unittest.TestCase):
    def response(self, content, finish='stop'):
        return SimpleNamespace(model='fixture',usage=None,choices=[SimpleNamespace(message=SimpleNamespace(content=content),finish_reason=finish)])

    def test_only_explicit_per_claim_ids_are_rendered(self):
        raw=json.dumps({'claims':[{'text':'Use the approved procedure.','source_ids':[2,2]},{'text':'Then verify access.','source_ids':[1]}]})
        answer, details=render_cited_output(raw,3)
        self.assertEqual(answer,'Use the approved procedure. [Source 2]\n\nThen verify access. [Source 1]')
        self.assertNotIn('[Source 3]',answer)
        self.assertEqual(details['claim_count'],2)

    def test_invalid_or_missing_attribution_rejects_whole_answer(self):
        payloads=[{'claims':[]}, {'claims':[{'text':'Claim.'}]}, {'claims':[{'text':'Claim.','source_ids':[]}]},
            {'claims':[{'text':'Claim.','source_ids':[1]},{'text':'Unattributed.','source_ids':[]}]},
            {'answer':'An answer [Source 1].'}, [{'text':'Claim [Source 1]','source_ids':[1]}]]
        for ids in ([0],[2],['1'],[True],[1.0],None):
            payloads.append({'claims':[{'text':'Claim.','source_ids':ids}]})
        for payload in payloads:
            with self.subTest(payload=payload):
                answer, details=render_cited_output(json.dumps(payload),1)
                self.assertEqual(answer,'')
                self.assertIsNotNone(details['error'])
        self.assertEqual(render_cited_output('{"claims":',1)[1]['error'],'invalid_json')

    def test_existing_supported_markdown_is_not_repaired_or_relabelled(self):
        for raw in ('[SOURCE 1] A supported answer.','【Source 1】 A supported answer.',
                    '[Vendor](https://vendor.example) instructions [Source 1].','Uncited answer.'):
            self.assertEqual(render_cited_output(raw,1)[0],raw)

    def test_real_generators_render_then_enforce_unchanged_guard_without_retry(self):
        private='private-policy employee@example.invalid'
        inputs=[(answer_generator,answer_generator.generate_answer,[{'id':'one','source':'policy.md','text':private}],800),
                (web_answer_generator,web_answer_generator.generate_web_answer,[{'title':'Vendor','url':'https://vendor.example','content':private}],1500)]
        raw=json.dumps({'claims':[{'text':'Supported claim.','source_ids':[1]}]})
        for module,generate,context,budget in inputs:
            for content,finish,accepted in [(raw,'stop',True),(raw,'length',False),
                    (json.dumps({'claims':[{'text':'Claim.','source_ids':[99]}]}),'stop',False),
                    (json.dumps({'claims':[{'text':'Claim [Source 99].','source_ids':[1]}]}),'stop',False),
                    ('Claim without attribution.','stop',False)]:
                with self.subTest(module=module.__name__,finish=finish,content=content), patch.object(module.client.chat.completions,'create',return_value=self.response(content,finish)) as request, redirect_stdout(io.StringIO()) as output, patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
                    result=generate('What should I do?',context)
                request.assert_called_once()
                self.assertEqual(request.call_args.kwargs['response_format'],{'type':'json_object'})
                self.assertEqual(request.call_args.kwargs['max_tokens'],budget)
                self.assertEqual(bool(result.get('grounded',True)),accepted)
                if accepted:
                    self.assertEqual(result['answer'],'Supported claim. [Source 1]')
                else:
                    self.assertEqual(result['sources'],[])
                self.assertNotIn(private,output.getvalue())
                self.assertNotIn(private,json.dumps(result['generation_diagnostics']))
                self.assertNotIn('Supported claim.',json.dumps(result['generation_diagnostics']))

    def test_structured_ids_do_not_bypass_expected_document_coverage(self):
        chunks=[{'id':'vpn','document_id':'vpn_troubleshooting'}, {'id':'software','document_id':'software_requests_and_installation'}]
        sources=[{'source_id':1,'chunk_id':'vpn'}, {'source_id':2,'chunk_id':'software'}]
        case={'expected_status':'answered','expected_document_ids':['KB-NET-0042','KB-SW-0008']}
        for ids,expected in [([1],False),([1,2],True)]:
            answer,_=render_cited_output(json.dumps({'claims':[{'text':'Claim.','source_ids':ids}]}),2)
            checks,_=score_knowledge(case,{'status':'answered','answer':answer,'retrieved_chunks':chunks,'sources':sources})
            self.assertEqual(checks['expected_documents_actually_cited'],expected)
