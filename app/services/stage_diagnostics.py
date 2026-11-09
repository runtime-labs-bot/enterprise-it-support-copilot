"""Opt-in, content-free stage tracing that survives a failed graph invocation."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

REQUIRED_STAGES = ('retrieval','relevance_grading','answer_generation','citation_safeguard')
_capture = ContextVar('stage_diagnostic_capture', default=None)
_active = ContextVar('active_diagnostic_stage', default=None)


@contextmanager
def capture_stages(records):
    token = _capture.set(records)
    try:
        yield records
    finally:
        _capture.reset(token)


def _timeout_category(error):
    categories = {'ReadTimeout':'read','ReadTimeoutError':'read','ConnectTimeout':'connect',
                  'ConnectTimeoutError':'connect','WriteTimeout':'write','PoolTimeout':'pool',
                  'TimeoutExpired':'case_deadline','TimeoutError':'unspecified'}
    kind = getattr(error,'transport_error',None) or type(error).__name__
    return categories.get(kind)


@contextmanager
def stage(name, *, provider=None, model=None, retry_count=None, component=None, llm=False):
    records = _capture.get()
    if records is None:
        yield None
        return
    if name not in (*REQUIRED_STAGES,'classification'):
        raise ValueError('Unsupported diagnostic stage')
    event = {'stage':name,'component':component,'provider':provider,'model':model,
             'status':'running','elapsed_seconds':None,'timeout_category':None,
             'timeout_seconds':None,'retry_count':retry_count,'request_count':0 if llm else None}
    if llm:
        # Metadata only. A configuration failure must not change application behavior.
        try:
            from app.services.llm_provider import get_config
            config=get_config(require_key=False)
            event.update(provider=config.provider,model=config.model,timeout_seconds=config.timeout,retry_count=0)
        except (ValueError,OSError):
            pass
    records.append(event)
    token = _active.set(event)
    started = time.perf_counter()
    try:
        yield event
        if event['status']=='running':
            event['status']='completed'
    except Exception as error:
        event.update(status='error',error_type=type(error).__name__,timeout_category=_timeout_category(error))
        status = getattr(error,'status_code',None)
        if type(status) is int and 100 <= status <= 599:
            event['http_status']=status
        raise
    finally:
        event['elapsed_seconds']=round(time.perf_counter()-started,6)
        _active.reset(token)


def note_llm_request(config):
    event = _active.get()
    if event is not None:
        event.update(provider=config.provider,model=config.model,timeout_seconds=config.timeout,retry_count=0)
        event['request_count']+=1
        event['phase_timeouts_seconds']={name:config.timeout for name in ('connect','read','write','pool')}


def finalize_stages(records):
    result = [dict(record) for record in records]
    seen = {record['stage'] for record in records}
    for name in REQUIRED_STAGES:
        if name not in seen:
            result.append({'stage':name,'component':None,'provider':None,'model':None,
                           'status':'not_run','elapsed_seconds':None,'timeout_category':None,
                           'timeout_seconds':None,'retry_count':None,'request_count':0})
    return result
