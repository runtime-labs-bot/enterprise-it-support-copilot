"""One explicit, lazy provider boundary for sync RAG and async tool calling."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import httpx
from dotenv import dotenv_values
from app.services.stage_diagnostics import note_llm_request

ROOT = Path(__file__).resolve().parents[2]
PRESETS = {
    'groq': ('https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
    'openai': ('https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'gemini': ('https://generativelanguage.googleapis.com/v1beta/openai', 'GEMINI_API_KEY'),
    'ollama': ('http://127.0.0.1:11434/v1', 'OLLAMA_API_KEY'),
    'compatible': ('', 'LLM_API_KEY'),
}
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', 'host.docker.internal'}
SELECTORS = ('LLM_PROVIDER','LLM_MODEL','LLM_BASE_URL','LLM_TOKEN_PARAMETER','LLM_TEMPERATURE_MODE','LLM_TIMEOUT_SECONDS')


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    key_variable: str
    api_key: str = field(repr=False)
    token_parameter: str = 'max_tokens'
    send_temperature: bool = True
    timeout: float = 30

    @classmethod
    def from_values(cls, values, require_key=True):
        provider = (values.get('LLM_PROVIDER') or 'groq').strip().lower()
        if provider not in PRESETS:
            raise ValueError('LLM_PROVIDER must be one of: ' + ', '.join(PRESETS))
        default_url, key_name = PRESETS[provider]
        base = (values.get('LLM_BASE_URL') or default_url).rstrip('/')
        if provider in {'groq', 'openai', 'gemini'} and base != default_url:
            raise ValueError('Use the compatible profile and LLM_API_KEY for custom endpoints')
        url = urlsplit(base)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Provide a base URL without credentials, query or fragment')
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in LOCAL_HOSTS):
            raise ValueError('Use HTTPS for remote providers; HTTP is supported for local servers')
        default_model = (values.get('GROQ_MODEL') or 'openai/gpt-oss-20b') if provider == 'groq' else ''
        model = (values.get('LLM_MODEL') or default_model).strip()
        if not model:
            raise ValueError('Set LLM_MODEL to a model supported by the selected provider')
        key = values.get(key_name) or ''
        if require_key and not key and not (provider in {'ollama','compatible'} and url.hostname in LOCAL_HOSTS):
            raise ValueError('Set ' + key_name + ' in the private environment configuration')
        token = values.get('LLM_TOKEN_PARAMETER') or ('max_completion_tokens' if provider == 'openai' else 'max_tokens')
        if token not in {'max_tokens', 'max_completion_tokens'}:
            raise ValueError('LLM_TOKEN_PARAMETER must be max_tokens or max_completion_tokens')
        temperature = values.get('LLM_TEMPERATURE_MODE') or 'auto'
        if temperature not in {'auto','send','omit'}:
            raise ValueError('LLM_TEMPERATURE_MODE must be auto, send or omit')
        try:
            timeout = float(values.get('LLM_TIMEOUT_SECONDS') or 30)
        except (TypeError, ValueError):
            raise ValueError('LLM_TIMEOUT_SECONDS must be 1–300') from None
        if not 1 <= timeout <= 300:
            raise ValueError('LLM_TIMEOUT_SECONDS must be 1–300')
        return cls(provider, model, base, key_name, key, token,
                   temperature == 'send' or (temperature == 'auto' and provider != 'openai'), timeout)


def get_config(require_key=True):
    # Read at call time: no import-time credentials or stale module-level model.
    local = dotenv_values(Path(os.getenv('LLM_ENV_FILE') or ROOT/'.env'), interpolate=False)
    values = {**local, **os.environ}
    # dotenv is also loaded elsewhere in this app. Local file selectors must win
    # over those stale copies for the CLI switch to take effect without a restart.
    # Container images do not contain .env; injected environment remains authoritative.
    for name in SELECTORS:
        if name in local:
            values[name] = local[name]
    for _, key in PRESETS.values():
        values[key] = os.environ.get(key) or local.get(key) or ''
    if os.getenv('SCORECARD_OFFLINE') == '1':
        values.update(LLM_PROVIDER='groq', LLM_MODEL='offline-model', LLM_BASE_URL='', GROQ_API_KEY='offline-placeholder')
    return LLMConfig.from_values(values, require_key)


class LLMProviderError(RuntimeError):
    def __init__(self, provider, status_code=None, headers=None, error_kind='http_status', transport_error=None):
        self.status_code = status_code
        self.error_kind = error_kind
        self.transport_error = transport_error
        allowed = {'retry-after', 'x-ratelimit-reset-tokens', 'x-ratelimit-reset-requests', 'date'}
        self.reset_headers = {k.lower():str(v)[:128] for k,v in (headers or {}).items() if k.lower() in allowed}
        super().__init__(f'{provider} completion failed' + (f' (HTTP {status_code})' if status_code else ''))


def _body(config, arguments):
    body = dict(arguments)
    if 'model' in body and body['model'] != config.model:
        raise ValueError('Select the model through LLM_MODEL, not a graph node')
    body['model'] = config.model
    limit = body.pop('max_tokens', None)
    alternate = body.pop('max_completion_tokens', None)
    if limit is not None and alternate is not None:
        raise ValueError('Specify only one completion token limit')
    if limit is not None or alternate is not None:
        body[config.token_parameter] = limit if limit is not None else alternate
    if not config.send_temperature:
        body.pop('temperature', None)
    return body


def _headers(config):
    return {'Authorization':'Bearer ' + config.api_key} if config.api_key else {}


def tool_call_for_history(call):
    """Keep Gemini's opaque tool signature in this in-memory model conversation."""
    result = {'id':call.id, 'type':'function', 'function':{
        'name':call.function.name, 'arguments':call.function.arguments}}
    extra = getattr(call, 'extra_content', None)
    google = getattr(extra, 'google', None)
    signature = getattr(google, 'thought_signature', None)
    if isinstance(signature,str):
        result['extra_content'] = {'google':{'thought_signature':signature}}
    return result


def _normalize(response, config):
    if not 200 <= response.status_code < 300:
        raise LLMProviderError(config.provider, response.status_code, response.headers)
    try:
        data = response.json()
        choices = data['choices']
        if not isinstance(choices, list) or not choices:
            raise ValueError()
        for choice in choices:
            message = choice['message']
            if not isinstance(message.get('content'), (str,type(None))):
                raise ValueError()
            # Tool-only completions may omit content. Empty text still reaches
            # the existing fail-closed citation guard on generation paths.
            message.setdefault('content', None)
            calls = message.get('tool_calls') or []
            for call in calls:
                if not all(isinstance(value,str) for value in (call['id'],call['function']['name'],call['function']['arguments'])):
                    raise ValueError()
            message.setdefault('tool_calls', [])
            choice.setdefault('finish_reason', None)
            if not isinstance(choice['finish_reason'], (str,type(None))):
                raise ValueError()
        data.setdefault('usage', None)
        data.setdefault('model', config.model)
        if not isinstance(data['model'],str) or not isinstance(data['usage'],(dict,type(None))):
            raise ValueError()
        def namespace(value):
            if isinstance(value, dict):
                return SimpleNamespace(**{k:namespace(v) for k,v in value.items()})
            return [namespace(v) for v in value] if isinstance(value,list) else value
        return namespace(data)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise LLMProviderError(config.provider, response.status_code, error_kind='invalid_response') from None


class _SyncCompletions:
    def create(self, **arguments):
        config = get_config()
        note_llm_request(config)
        try:
            with httpx.Client(timeout=config.timeout, trust_env=False, follow_redirects=False) as client:
                response = client.post(config.base_url + '/chat/completions', headers=_headers(config), json=_body(config,arguments))
        except httpx.RequestError as error:
            raise LLMProviderError(config.provider, error_kind='transport', transport_error=type(error).__name__) from None
        return _normalize(response,config)


class LLMClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_SyncCompletions())


class AsyncLLMClient:
    async def __aenter__(self):
        self.config = get_config()
        self.client = httpx.AsyncClient(timeout=self.config.timeout, trust_env=False, follow_redirects=False)
        self.chat = SimpleNamespace(completions=self)
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def create(self, **arguments):
        note_llm_request(self.config)
        try:
            response = await self.client.post(self.config.base_url + '/chat/completions', headers=_headers(self.config), json=_body(self.config,arguments))
        except httpx.RequestError as error:
            raise LLMProviderError(self.config.provider, error_kind='transport', transport_error=type(error).__name__) from None
        return _normalize(response,self.config)
