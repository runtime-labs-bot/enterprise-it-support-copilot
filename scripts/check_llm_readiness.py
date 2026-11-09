"""Explicit one-request readiness gate. Does not resume evaluation by itself."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.llm_provider import PRESETS,SELECTORS
from app.evaluation.readiness import check_readiness


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Authorize exactly one model request')
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--rate-limit-report',action='append',type=Path,default=[],help='Saved reports to check before making the readiness request')
    args=parser.parse_args()
    if not args.live:
        parser.error('Pass --live to explicitly request one readiness completion')
    if not args.env_file.is_file():
        parser.error('Configuration file does not exist')
    output=args.output
    if output is None:
        number=1
        while (ROOT/f'evals/reports/llm-readiness-{number:03}.json').exists():
            number+=1
        output=ROOT/f'evals/reports/llm-readiness-{number:03}.json'
    if output.exists():
        parser.error('Readiness report exists; choose a fresh path')
    values=dotenv_values(args.env_file,interpolate=False)
    os.environ['LLM_ENV_FILE']=str(args.env_file.resolve())
    for key in (*SELECTORS,*(key for _,key in PRESETS.values())):
        if values.get(key) is not None:
            os.environ[key]=values[key]
    from app.services.llm_provider import get_config
    from app.evaluation.rate_limits import active_cooldown
    try:
        provider=get_config(require_key=False).provider
    except ValueError:
        provider=None
    cooldown=active_cooldown([*args.rate_limit_report,*output.parent.glob('batch-*.json')],provider)
    result=({'ready':False,'provider_limited':True,'reason':'Provider reset window is still active; no live call made','retry_window':cooldown}
            if cooldown else check_readiness())
    result['created_at']=datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    print('Readiness report: '+str(output))
    return 0 if result['ready'] else 1


if __name__=='__main__':
    raise SystemExit(main())
