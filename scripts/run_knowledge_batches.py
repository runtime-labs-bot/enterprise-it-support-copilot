"""Run remaining knowledge cases in resumable batches using existing scorecards."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.evaluation.scorecard import catalog, fingerprint, markdown, report, row, transport_failure
from app.evaluation.rate_limits import active_cooldown


def origin(outcome, data, path, seen=None):
    """Resolve nested coverage seeds back to an actual provider-labelled attempt."""
    seen = set() if seen is None else seen
    if outcome.get('source_provenance'):
        return outcome.get('source_report', str(path)), outcome['source_provenance']
    if data.get('provenance'):
        return str(path), {'provider':'not_recorded', **data['provenance']}
    source = outcome.get('source_report')
    if source and source not in seen:
        seen.add(source)
        candidate = Path(source)
        try:
            previous = json.loads(candidate.read_text(encoding='utf-8'))
            matching = next(item for item in previous['results'] if item['id'] == outcome['id'])
            if matching.get('expectation_hash') == outcome.get('expectation_hash'):
                return origin(matching, previous, candidate, seen)
        except (OSError, ValueError, KeyError, StopIteration):
            pass
    return source or str(path), {'provider':'unknown', 'model':'unknown'}


def save_progress(cases, paths, output_dir):
    """Report all requested knowledge cases, including those not yet attempted."""
    outcomes, source_runs = {}, []
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        source_runs.append({'path':str(path), 'created_at':data.get('created_at'), 'provenance':data.get('provenance')})
        for outcome in data['results']:
            if outcome['id'] not in cases or outcome.get('expectation_hash') != fingerprint(cases[outcome['id']]):
                raise ValueError('Report expectations differ from current catalog: ' + str(path))
            if outcome.get('status') not in {'passed','failed','error','skipped'}:
                raise ValueError('Invalid case status: ' + str(path))
            # Completed baseline observations, including failures, are immutable.
            if outcomes.get(outcome['id'], {}).get('status') in {'passed','failed'}:
                continue
            source, provenance = origin(outcome, data, path)
            outcomes[outcome['id']] = {**outcome, 'source_report':source, 'source_provenance':provenance}
    results = [row(case, outcomes.get(case['id'], {'status':'skipped', 'reason':'Not yet evaluated'})) for case in cases.values()]
    data = report(results)
    data['source_runs'] = source_runs
    data['selection_policy'] = 'Preserve first completed outcome; retry only errors/skips; retain every attempt'
    data['coverage'] = {'completed':sum(r['status'] in {'passed','failed'} for r in results), 'remaining':sum(r['status'] not in {'passed','failed'} for r in results), 'never_requested':sum(r.get('reason') == 'Not yet evaluated' for r in results)}
    (output_dir / 'coverage.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    labels = ['','## Provider and model by case','','Mixed-provider completion tracking, not a single-provider quality score.','',
              '| Case | Outcome | Provider | Model |','| --- | --- | --- | --- |']
    for result in results:
        provenance = result.get('source_provenance') or {}
        labels.append(f"| {result['id']} | {result['status']} | {provenance.get('provider', 'Not run')} | {provenance.get('model', 'Not run')} |")
    (output_dir / 'coverage.md').write_text(markdown(data)+'\n'.join(labels)+'\n', encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exclude-report', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--delay', type=float, default=10)
    parser.add_argument('--max-batches', type=int, help='Bound this invocation without changing resume coverage')
    parser.add_argument('--timeout', type=int, default=120, help='Whole-case deadline in seconds')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20 or not 0 <= args.delay <= 60:
        parser.error('batch-size must be 1..20 and delay 0..60')
    if (args.max_batches is not None and args.max_batches < 1) or not 1 <= args.timeout <= 3600:
        parser.error('max-batches must be positive and timeout must be 1..3600')
    cases = {c['id']: c for c in catalog() if c['profile'] == 'knowledge'}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    def progress():
        return save_progress(cases, [args.exclude_report, *sorted(args.output_dir.glob('batch-*.json'))], args.output_dir)
    try:
        data = progress()
    except (OSError, ValueError, KeyError) as error:
        parser.error('Cannot resume reports: ' + str(error))
    completed = {outcome['id'] for outcome in data['results'] if outcome['status'] in {'passed','failed'}}
    remaining = [key for key in cases if key not in completed]
    from app.services.llm_provider import get_config
    try:
        provider = get_config(require_key=False).provider
    except ValueError:
        provider = None
    cooldown = active_cooldown([args.exclude_report, *args.output_dir.glob('batch-*.json')], provider)
    if remaining and cooldown:
        print('Provider reset window is still active; no live calls made. '+json.dumps(cooldown), flush=True)
        return 1
    transport_errors = 0
    for offset in range(0, len(remaining), args.batch_size):
        if args.max_batches is not None and offset // args.batch_size >= args.max_batches:
            break
        # The worker waits between cases but skips its final delay. Preserve the
        # same spacing across subprocess/batch boundaries, too.
        if offset and args.delay:
            time.sleep(args.delay)
        ids = remaining[offset:offset + args.batch_size]
        # Never overwrite historical attempts, including timeouts/quota errors.
        index = 1
        while (args.output_dir / f'batch-{index:03}.json').exists():
            index += 1
        output = args.output_dir / f'batch-{index:03}'
        print(f'Running {output.name}: {", ".join(ids)}', flush=True)
        result = subprocess.run([sys.executable, '-B', '-m', 'app.evaluation.scorecard', '--profile', 'knowledge', '--ids', ','.join(ids), '--limit', str(len(ids)), '--delay', str(args.delay), '--timeout', str(args.timeout), '--transport-failure-limit', str(2-transport_errors), '--output', str(output)], cwd=ROOT)
        if result.returncode not in (0, 1) or not output.with_suffix('.json').exists():
            return 2
        report = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
        progress()
        transport_errors += sum(transport_failure(item) for item in report['results'])
        if transport_errors >= 2 or any(item.get('provider_limited') or (item.get('status') == 'error' and not transport_failure(item)) for item in report['results']):
            print('Provider limit, repeated transport failures or evaluation error; reports preserved.', flush=True)
            return 1
    return 0 if progress()['summary']['gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
