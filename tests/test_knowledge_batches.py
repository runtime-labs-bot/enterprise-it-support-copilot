import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.evaluation.scorecard import row, run_knowledge
from scripts.run_knowledge_batches import save_progress
from scripts.run_knowledge_batches import main


class KnowledgeBatchTests(unittest.TestCase):
    def test_case_spacing_crosses_batch_boundaries_without_sleep_after_stop(self):
        cases = [self.case(str(i)) for i in range(4)]
        for limited, maximum in [(False,2),(True,2),(False,1)]:
            with self.subTest(limited=limited,maximum=maximum), TemporaryDirectory() as directory:
                folder=Path(directory);seed=folder/'seed.json';seed.write_text(json.dumps({'results':[]}))
                events=[]
                def execute(command, **kwargs):
                    ids=command[command.index('--ids')+1].split(',')
                    events.append(('batch',ids))
                    self.assertEqual(command[command.index('--delay')+1],'60.0')
                    results=[row(next(c for c in cases if c['id']==key),
                        {'status':'error','provider_limited':True,'http_status':429} if limited else {'status':'passed'}) for key in ids]
                    Path(command[command.index('--output')+1]).with_suffix('.json').write_text(json.dumps({'results':results}))
                    return SimpleNamespace(returncode=1 if limited else 0)
                arguments=['runner','--exclude-report',str(seed),'--output-dir',str(folder),
                    '--batch-size','2','--delay','60','--max-batches',str(maximum)]
                with patch('sys.argv',arguments), patch('scripts.run_knowledge_batches.catalog',return_value=cases), patch('scripts.run_knowledge_batches.active_cooldown',return_value=None), patch('scripts.run_knowledge_batches.subprocess.run',side_effect=execute), patch('scripts.run_knowledge_batches.time.sleep',side_effect=lambda seconds:events.append(('sleep',seconds))):
                    main()
                expected=[('batch',['0','1'])]
                if not limited and maximum==2:
                    expected += [('sleep',60.0),('batch',['2','3'])]
                self.assertEqual(events,expected)

    def test_first_service_error_stops_for_explicit_fallback_without_hiding_prior_results(self):
        cases = [self.case(str(i)) for i in range(4)]
        outcomes = [{'status':'failed'}, {'status':'passed'}, {'status':'error','provider_error_kind':'http_status','http_status':503}]
        with patch('app.evaluation.scorecard.subprocess.run',side_effect=[SimpleNamespace(returncode=0,stdout=json.dumps(item)) for item in outcomes]) as request:
            results = run_knowledge(cases,stop_on_error=True)
        self.assertEqual(request.call_count,3)
        self.assertEqual([item['status'] for item in results],['failed','passed','error','skipped'])
        self.assertIn('fallback',results[-1]['reason'])

    def test_original_failure_and_nested_provider_are_preserved(self):
        case = self.case('one')
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            raw = folder/'groq.json'
            raw.write_text(json.dumps({'results':[row(case, {'status':'failed'})], 'provenance':{'provider':'groq','model':'groq-fixture'}}))
            seed = folder/'seed.json'
            seed.write_text(json.dumps({'results':[{**row(case, {'status':'failed'}), 'source_report':str(raw)}]}))
            new = folder/'gemini.json'
            new.write_text(json.dumps({'results':[row(case, {'status':'passed'})], 'provenance':{'provider':'gemini','model':'gemini-fixture'}}))
            data = save_progress({'one':case},[seed,new],folder)
            self.assertEqual(data['results'][0]['status'],'failed')
            self.assertEqual(data['results'][0]['source_provenance']['provider'],'groq')
            self.assertEqual(data['results'][0]['source_report'],str(raw))
            self.assertIn('groq-fixture',(folder/'coverage.md').read_text())

    def test_old_model_only_provenance_does_not_claim_provider_was_recorded(self):
        case = self.case('one')
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder/'old.json'
            path.write_text(json.dumps({'results':[row(case, {'status':'passed'})], 'provenance':{'model':'historical-model'}}))
            data = save_progress({'one':case},[path],folder)
            self.assertEqual(data['results'][0]['source_provenance']['provider'],'not_recorded')
            self.assertEqual(data['results'][0]['source_provenance']['model'],'historical-model')

    def test_transport_stop_checkpoints_each_completed_case_and_skips_remaining(self):
        cases = [self.case(str(i)) for i in range(4)]
        error = {'status':'error','provider_error_kind':'transport','transport_error':'ReadTimeout'}
        snapshots = []
        with patch('app.evaluation.scorecard.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(error))) as request:
            result = run_knowledge(cases,transport_failure_limit=2,on_result=lambda results:snapshots.append(json.loads(json.dumps(results))))
        self.assertEqual(request.call_count,2)
        self.assertEqual([r['status'] for r in result],['error','error','skipped','skipped'])
        self.assertEqual(len(snapshots),4)
        self.assertEqual(len(snapshots[0]),1)

    def test_rate_limit_stops_immediately_and_keeps_prior_pass(self):
        cases = [self.case(str(i)) for i in range(3)]
        outcomes = [{'status':'passed'},{'status':'error','provider_limited':True,'http_status':429}]
        with patch('app.evaluation.scorecard.subprocess.run',side_effect=[SimpleNamespace(returncode=0,stdout=json.dumps(item)) for item in outcomes]) as request:
            result = run_knowledge(cases,transport_failure_limit=2)
        self.assertEqual(request.call_count,2)
        self.assertEqual([r['status'] for r in result],['passed','error','skipped'])

    def test_bounded_resume_and_error_stop_preserve_sources(self):
        cases = [self.case(str(i)) for i in range(4)]
        for status, maximum, expected_calls in [('passed', 1, 1), ('error', 3, 1)]:
            with self.subTest(status=status), TemporaryDirectory() as directory:
                folder = Path(directory)
                seed = folder/'seed.json'
                original = json.dumps({'results':[]}).encode()
                seed.write_bytes(original)
                calls = []
                def execute(command, **kwargs):
                    calls.append(command)
                    ids = command[command.index('--ids')+1].split(',')
                    output = Path(command[command.index('--output')+1]).with_suffix('.json')
                    output.write_text(json.dumps({'results':[row(next(c for c in cases if c['id']==key), {'status':status}) for key in ids]}))
                    return SimpleNamespace(returncode=0 if status=='passed' else 1)
                arguments = ['runner','--exclude-report',str(seed),'--output-dir',str(folder),
                             '--batch-size','2','--max-batches',str(maximum),'--timeout','120']
                with patch('sys.argv',arguments), patch('scripts.run_knowledge_batches.catalog',return_value=cases), patch('scripts.run_knowledge_batches.subprocess.run',side_effect=execute):
                    main()
                self.assertEqual(len(calls),expected_calls)
                self.assertEqual(calls[0][calls[0].index('--timeout')+1],'120')
                self.assertEqual(seed.read_bytes(),original)
                self.assertTrue((folder/'coverage.json').exists())

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
