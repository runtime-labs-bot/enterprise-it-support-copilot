"""Safe generation evidence: counts, digests and rejection codes, never content."""
from hashlib import sha256
from contextlib import contextmanager
from contextvars import ContextVar
import re
from app.services.citations import citation_validation
from app.services.stage_diagnostics import stage
from app.services.cited_output import render_cited_output

_keywords = ContextVar('generation_diagnostic_keywords', default=())


@contextmanager
def probe_generation(keywords):
    """Evaluation-only lexical probes; never retain the candidate's contents."""
    token = _keywords.set(tuple(keywords))
    try:
        yield
    finally:
        _keywords.reset(token)


def assess_generation(response, context, source_count, source_kind, requested_max_tokens):
    choice = response.choices[0]
    raw = choice.message.content or ''
    finish = choice.finish_reason
    usage = getattr(response, 'usage', None)
    details = getattr(usage, 'completion_tokens_details', None)
    def count(obj, name):
        value = getattr(obj, name, None)
        return value if type(value) is int and value >= 0 else None
    with stage('citation_safeguard', component=source_kind, llm=True) as event:
        answer, formatting = render_cited_output(raw, source_count)
        validation = citation_validation(answer, source_count, finish)
        if formatting['error']:
            validation['accepted'] = False
            validation['rejection_reasons'].append('invalid_citation_output')
        if event is not None:
            event['retry_count'] = 0
            event['timeout_seconds'] = None
            event['execution'] = 'local_validation'
            if not validation['accepted']:
                event['status'] = 'rejected'
                event['rejection_reasons'] = validation['rejection_reasons']
    data = {
        'source_kind': source_kind,
        'finish_reason': finish if finish in {'stop','length','content_filter','tool_calls','function_call'} else 'unknown',
        'candidate_characters': len(raw),
        'candidate_sha256': sha256(raw.encode()).hexdigest(),
        'rendered_characters': len(answer),
        'rendered_sha256': sha256(answer.encode()).hexdigest(),
        'citation_output': formatting,
        'context_characters': len(context),
        'context_sha256': sha256(context.encode()).hexdigest(),
        'prompt_tokens': count(usage, 'prompt_tokens'),
        'completion_tokens': count(usage, 'completion_tokens'),
        'reasoning_tokens': count(details, 'reasoning_tokens'),
        'requested_max_tokens': requested_max_tokens,
        'validation': validation,
    }
    if _keywords.get():
        data['literal_expected_keyword_presence'] = {
            keyword: bool(re.search(r'(?<!\w)' + re.escape(keyword) + r'(?!\w)', answer, re.I))
            for keyword in _keywords.get()
        }
    return answer, data
