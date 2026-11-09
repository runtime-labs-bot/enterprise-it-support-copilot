"""Exactly one minimal JSON completion; no retrieval or employee data."""
import json
from app.services.llm_provider import LLMClient, get_config
from app.services.stage_diagnostics import capture_stages, stage, finalize_stages


def check_readiness():
    records=[]
    selection=None
    result={'ready':False}
    try:
        with capture_stages(records), stage('relevance_grading', component='readiness_json', llm=True) as event:
            selection=get_config(require_key=False)
            response=LLMClient().chat.completions.create(
                messages=[{'role':'system','content':'Return only the requested JSON object.'},
                          {'role':'user','content':'Return exactly this JSON object: {"ready":true}'}],
                response_format={'type':'json_object'},temperature=0,max_tokens=800)
            try:
                data=json.loads(response.choices[0].message.content or '')
            except (ValueError,TypeError):
                data=None
            result['ready']=isinstance(data,dict) and data.get('ready') is True and response.choices[0].finish_reason=='stop'
            if not result['ready']:
                event['status']='rejected'
                event['rejection_reasons']=['readiness_output_not_confirmed']
    except Exception as error:
        result.update(error_type=type(error).__name__)
        status=getattr(error,'status_code',None)
        if type(status) is int and 100 <= status <= 599:
            result['http_status']=status
        if status == 429 and getattr(error, 'reset_headers', None):
            from datetime import datetime, timezone
            from app.evaluation.rate_limits import retry_window
            result['rate_limit_headers'] = error.reset_headers
            result['retry_window'] = retry_window(error.reset_headers, datetime.now(timezone.utc).isoformat())
        if getattr(error,'transport_error',None) in {'ReadTimeout','ConnectTimeout','WriteTimeout','PoolTimeout','ConnectError','ReadError','WriteError','RemoteProtocolError','LocalProtocolError'}:
            result['transport_error']=error.transport_error
    result.update(provider=selection.provider if selection else None,model=selection.model if selection else None,
                  stage_diagnostics=finalize_stages(records))
    return result
