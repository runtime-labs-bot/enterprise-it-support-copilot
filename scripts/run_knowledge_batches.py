"""Run remaining knowledge cases in resumable batches using existing scorecards."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.evaluation.scorecard import catalog, fingerprint, markdown, report, row


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
            outcomes[outcome['id']] = {**outcome, 'source_report':str(path)}
    results = [row(case, outcomes.get(case['id'], {'status':'skipped', 'reason':'Not yet evaluated'})) for case in cases.values()]
    data = report(results)
    data['source_runs'] = source_runs
    data['selection_policy'] = 'Latest attempt per case; source reports are retained unchanged'
    data['coverage'] = {'completed':sum(r['status'] in {'passed','failed'} for r in results), 'remaining':sum(r['status'] not in {'passed','failed'} for r in results), 'never_requested':sum(r.get('reason') == 'Not yet evaluated' for r in results)}
    (output_dir / 'coverage.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    (output_dir / 'coverage.md').write_text(markdown(data), encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exclude-report', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--delay', type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20 or not 0 <= args.delay <= 60:
        parser.error('batch-size must be 1..20 and delay 0..60')
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
    for offset in range(0, len(remaining), args.batch_size):
        ids = remaining[offset:offset + args.batch_size]
        # Never overwrite historical attempts, including timeouts/quota errors.
        index = 1
        while (args.output_dir / f'batch-{index:03}.json').exists():
            index += 1
        output = args.output_dir / f'batch-{index:03}'
        print(f'Running {output.name}: {", ".join(ids)}', flush=True)
        result = subprocess.run([sys.executable, '-B', '-m', 'app.evaluation.scorecard', '--profile', 'knowledge', '--ids', ','.join(ids), '--limit', str(len(ids)), '--delay', str(args.delay), '--output', str(output)], cwd=ROOT)
        if result.returncode not in (0, 1) or not output.with_suffix('.json').exists():
            return 2
        report = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
        progress()
        if any(row.get('provider_limited') for row in report['results']):
            print('Provider limit reached; reports preserved. Resume with the same command later.', flush=True)
            return 1
    return 0 if progress()['summary']['gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
