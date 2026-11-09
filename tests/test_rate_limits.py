from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.evaluation.rate_limits import active_cooldown, duration, retry_window
from app.evaluation import scorecard
from scripts import check_llm_readiness

DATE = 'Sun, 08 Nov 2026 17:25:00 GMT'
HEADERS = {'date':DATE, 'retry-after':'1', 'x-ratelimit-reset-requests':'7m12s', 'x-ratelimit-reset-tokens':'53.79s'}
NOW = datetime(2026,11,8,17,26,tzinfo=timezone.utc)


class RateLimitTests(unittest.TestCase):
    def report(self, folder, provider='groq'):
        path = folder/'batch-001.json'
        path.write_text(json.dumps({'created_at':'2026-11-08T17:25:05+00:00',
            'provenance':{'provider':provider,'model':'fixture'},
            'results':[{'id':'one','status':'error','http_status':429,'rate_limit_headers':HEADERS}]}))
        return path

    def test_longest_saved_groq_interval_wins(self):
        window = retry_window(HEADERS, None)
        self.assertEqual(window['reset_interval_seconds'],432)
        self.assertEqual(window['retry_not_before_utc'],'2026-11-08T17:32:12+00:00')
        self.assertEqual(window['limiting_headers'],['x-ratelimit-reset-requests'])

    def test_fractional_composite_units_and_invalid_values(self):
        self.assertEqual(duration('1h2m3.5s'),3723.5)
        self.assertEqual(duration('1s500ms'),1.5)
        for value in ('NaN','inf','-1','1m junk','tomorrow',None,''):
            self.assertIsNone(duration(value))

    def test_retry_after_http_date_and_later_token_reset(self):
        headers = {'date':DATE,'retry-after':'Sun, 08 Nov 2026 17:27:00 GMT','x-ratelimit-reset-tokens':'3m'}
        self.assertEqual(retry_window(headers,None)['reset_interval_seconds'],180)

    def test_missing_date_uses_saved_observation_not_new_resume_time(self):
        headers = {'retry-after':'60'}
        self.assertEqual(retry_window(headers,'2026-11-08T17:25:00+00:00')['retry_not_before_utc'],'2026-11-08T17:26:00+00:00')
        self.assertIsNone(retry_window(headers,None))
        self.assertIsNone(retry_window({'date':DATE,'retry-after':'tomorrow'},None))

    def test_expiry_remaining_delay_and_provider_isolation(self):
        with TemporaryDirectory() as directory:
            path = self.report(Path(directory))
            self.assertEqual(active_cooldown([path],'groq',NOW)['wait_seconds'],372)
            self.assertIsNone(active_cooldown([path],'gemini',NOW))
            self.assertIsNone(active_cooldown([path],None,NOW))
            self.assertIsNone(active_cooldown([path],'groq',datetime(2026,11,8,17,32,12,tzinfo=timezone.utc)))

    def test_nested_coverage_and_gate_reports_keep_original_deadline(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            raw = self.report(folder)
            gate = folder/'gate.json'
            gate.write_text(json.dumps({'provenance':{'provider':'groq'},'results':[{'status':'skipped','retry_window':{'source_report':str(raw)}}]}))
            seed = folder/'seed.json'
            seed.write_text(json.dumps({'results':[{'source_report':str(gate)}]}))
            self.assertEqual(active_cooldown([seed],'groq',NOW)['wait_seconds'],372)

    def test_non_rate_errors_and_bad_files_do_not_invent_cooldowns(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);path=self.report(folder)
            data=json.loads(path.read_text());data['results'][0]['http_status']=503;path.write_text(json.dumps(data))
            bad=folder/'bad.json';bad.write_text('broken')
            self.assertIsNone(active_cooldown([path,bad,folder/'missing.json'],'groq',NOW))

    def test_scorecard_gate_prevents_worker_requests(self):
        case={'id':'one','profile':'knowledge','group':'policy_citations','critical':False,'expected_status':'answered'}
        cooldown={'provider':'groq','wait_seconds':372,'retry_not_before_utc':'2026-11-08T17:32:12+00:00'}
        with TemporaryDirectory() as directory, patch('sys.argv',['scorecard','--profile','knowledge','--ids','one','--output',str(Path(directory)/'new')]), patch.object(scorecard,'catalog',return_value=[case]), patch('app.services.llm_provider.get_config',return_value=SimpleNamespace(provider='groq')), patch('app.evaluation.rate_limits.active_cooldown',return_value=cooldown), patch.object(scorecard,'run_knowledge') as worker, patch.object(scorecard,'finish',return_value=1) as finish:
            self.assertEqual(scorecard.main(),1)
            worker.assert_not_called()
            self.assertEqual(finish.call_args.args[0][0]['status'],'skipped')
            self.assertEqual(finish.call_args.args[0][0]['retry_window']['wait_seconds'],372)

    def test_readiness_gate_prevents_network_and_saves_reason(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);config=folder/'selection.env';config.write_text('LLM_PROVIDER=groq\nLLM_MODEL=fixture\n')
            output=folder/'readiness.json'
            args=['readiness','--live','--env-file',str(config),'--output',str(output)]
            with patch('sys.argv',args), patch.dict('os.environ',{},clear=False), patch('app.services.llm_provider.get_config',return_value=SimpleNamespace(provider='groq')), patch('app.evaluation.rate_limits.active_cooldown',return_value={'provider':'groq','wait_seconds':372}), patch.object(check_llm_readiness,'check_readiness') as request:
                self.assertEqual(check_llm_readiness.main(),1)
                request.assert_not_called()
            self.assertFalse(json.loads(output.read_text())['ready'])
