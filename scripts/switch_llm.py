"""Select a provider without API calls; optionally rebuild/restart Docker Copilot."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.llm_provider import LLMConfig, PRESETS, SELECTORS


def switch(path, provider, model=None, base_url=None, temperature_mode='auto', token_parameter=None):
    local = dotenv_values(path, interpolate=False) if path.exists() else {}
    changes = {'LLM_PROVIDER':provider, 'LLM_MODEL':model or '', 'LLM_BASE_URL':base_url or '',
               'LLM_TEMPERATURE_MODE':temperature_mode, 'LLM_TOKEN_PARAMETER':token_parameter or ''}
    values = {**local, **os.environ, **changes}
    for _, key in PRESETS.values():
        values[key] = os.environ.get(key) or local.get(key) or ''
    config = LLMConfig.from_values(values)
    # Validate everything first; replace one task-owned temp file atomically.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.env.switch-', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(path.read_text(encoding='utf-8') if path.exists() else '')
    try:
        for key, value in changes.items():
            set_key(str(temporary), key, value)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', nargs='?', choices=tuple(PRESETS))
    parser.add_argument('--model', help='Exact model ID supported by that provider')
    parser.add_argument('--base-url', help='API base including /v1, without /chat/completions')
    parser.add_argument('--temperature-mode', choices=('auto','send','omit'), default='auto')
    parser.add_argument('--token-parameter', choices=('max_tokens','max_completion_tokens'))
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--docker', action='store_true', help='Configure .env.docker and rebuild/restart only Copilot')
    parser.add_argument('--show', action='store_true', help='Show selection without any API request or secret output')
    args = parser.parse_args()
    path = (args.env_file or ROOT/('.env.docker' if args.docker else '.env')).resolve()
    try:
        if args.show:
            file_values = dotenv_values(path, interpolate=False)
            values = {**file_values, **os.environ}
            for name in SELECTORS:
                file_value = file_values.get(name)
                if file_value is not None:
                    values[name] = file_value
            for _, key in PRESETS.values():
                values[key] = os.environ.get(key) or file_values.get(key) or ''
            config = LLMConfig.from_values(values, require_key=False)
        else:
            if not args.provider:
                parser.error('Specify a provider or --show')
            base = args.base_url
            if args.docker and args.provider == 'ollama' and not base:
                base = 'http://host.docker.internal:11434/v1'
            config = switch(path, args.provider, args.model, base, args.temperature_mode, args.token_parameter)
    except (ValueError, OSError):
        # Never print configuration contents, credentials or exception payloads.
        parser.exit(2, 'Provider configuration invalid or unavailable. Check the model, base URL and provider-specific API key; no provider calls were made.\n')
    print(f'Provider: {config.provider}; model: {config.model}; credentials: {config.key_variable} ({"configured" if config.api_key else "not set"})')
    if args.show:
        return 0
    if args.docker:
        env = {**os.environ, **{key:value for key,value in dotenv_values(path, interpolate=False).items() if key in SELECTORS and value is not None}}
        try:
            result = subprocess.run(['docker','compose','--env-file',str(path),'up','--build','-d','--wait','--no-deps','copilot'],cwd=ROOT,env=env)
        except OSError:
            print('Configuration saved, but Docker is unavailable. The service has not been verified or restarted.')
            return 1
        if result.returncode:
            print('Configuration saved, but Docker restart failed. The running service may still use its previous configuration.')
        return result.returncode
    print('Saved. Local LLM clients read the selection on subsequent calls. Docker deployments require --docker.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
