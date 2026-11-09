"""Content-free, provider-scoped retry windows from saved rate-limit evidence."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import math
from pathlib import Path
import re


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def duration(value):
    if not isinstance(value, str) or len(value) > 128:
        return None
    value = value.strip()
    if re.fullmatch(r'\d+(?:\.\d+)?', value):
        result = float(value)
    else:
        parts = re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h|d)', value)
        if not parts or ''.join(number+unit for number,unit in parts) != value:
            return None
        scales = {'ms':.001,'s':1,'m':60,'h':3600,'d':86400}
        result = sum(float(number)*scales[unit] for number,unit in parts)
    return result if math.isfinite(result) else None


def retry_window(headers, observed_at):
    """Use the maximum supported deadline, never invent a daily reset time."""
    headers = {str(key).lower():value for key,value in headers.items()}
    reference = timestamp(headers.get('date')) or timestamp(observed_at)
    if reference is None:
        return None
    candidates = {}
    for name in ('retry-after','x-ratelimit-reset-requests','x-ratelimit-reset-tokens'):
        value = headers.get(name)
        seconds = duration(value)
        if seconds is None:
            absolute = timestamp(value) if name == 'retry-after' else None
            seconds = max(0, (absolute-reference).total_seconds()) if absolute else None
        if seconds is not None:
            try:
                candidates[name] = reference+timedelta(seconds=seconds)
            except OverflowError:
                continue
    if not candidates:
        return None
    deadline = max(candidates.values())
    return {'retry_not_before_utc':deadline.isoformat(),
            'reset_interval_seconds':(deadline-reference).total_seconds(),
            'limiting_headers':[key for key,value in candidates.items() if value == deadline]}


def active_cooldown(paths, provider, now=None):
    """Follow coverage provenance so a new output directory retains old cooldowns."""
    now = now or datetime.now(timezone.utc)
    if not provider:
        return None
    pending = [Path(path) for path in paths]
    seen = set()
    windows = []
    while pending:
        path = pending.pop()
        identity = str(path.resolve())
        if identity in seen:
            continue
        seen.add(identity)
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        rows = data.get('results', [data])
        for item in rows:
            if item.get('source_report'):
                pending.append(Path(item['source_report']))
            window_source = (item.get('retry_window') or {}).get('source_report')
            if window_source:
                pending.append(Path(window_source))
            selection = item.get('source_provenance') or data.get('provenance') or data
            if selection.get('provider') != provider:
                continue
            if not (item.get('provider_limited') or item.get('http_status') == 429):
                continue
            window = retry_window(item.get('rate_limit_headers') or {}, data.get('created_at'))
            if window and timestamp(window['retry_not_before_utc']) > now:
                windows.append({**window,'source_report':str(path),'provider':provider})
    if not windows:
        return None
    result = max(windows,key=lambda item:timestamp(item['retry_not_before_utc']))
    return {**result,'wait_seconds':math.ceil((timestamp(result['retry_not_before_utc'])-now).total_seconds())}
