import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.evaluation.scorecard import row
from scripts.run_knowledge_batches import save_progress


class KnowledgeBatchTests(unittest.TestCase):
    def case(self, name):
        return {'id':name, 'profile':'knowledge', 'group':'policy_citations', 'critical':False, 'expected_status':'answered'}

    def test_full_denominator_includes_unrun_and_errors_and_preserves_failed_attempts(self):
        cases = {name:self.case(name) for name in ('one','two','three','four')}
        with TemporaryDirectory() as directory:
            output = Path(directory)
            first = output / 'batch-001.json'
            original = json.dumps({'results':[row(cases['one'], {'status':'failed'}),row(cases['two'], {'status':'error','provider_limited':True})]}).encode()
            first.write_bytes(original)
            second = output / 'batch-002.json'
            second.write_text(json.dumps({'results':[row(cases['two'], {'status':'passed'}),row(cases['three'], {'status':'skipped'})]}))
            result = save_progress(cases,[first,second],output)
            self.assertEqual(result['summary']['total'],4)
            self.assertEqual(result['summary']['passed'],1)
            self.assertEqual(result['summary']['failed'],1)
            self.assertEqual(result['coverage'], {'completed':2,'remaining':2,'never_requested':1})
            self.assertFalse(result['summary']['gate_passed'])
            self.assertEqual(first.read_bytes(),original)
            self.assertEqual(result['results'][1]['source_report'],str(second))

    def test_resume_rejects_changed_expectations_and_invalid_status(self):
        case = self.case('one')
        with TemporaryDirectory() as directory:
            output=Path(directory)
            path=output/'bad.json'
            for outcome in ({**row(case,{'status':'passed'}),'expectation_hash':'changed'},row(case,{'status':'unknown'})):
                path.write_text(json.dumps({'results':[outcome]}))
                with self.assertRaises(ValueError):
                    save_progress({'one':case},[path],output)
