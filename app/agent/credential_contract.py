"""Source-free handling of explicit secret disclosure requests and offers."""
import re
import unicodedata

REFUSAL = (
    "I can't retrieve, reveal, or collect passwords, API keys, one-time codes, "
    "or other secret credentials. Don't paste secrets into chat. Use your approved "
    "account recovery or credential-management flow instead. "
    "Could you describe the sign-in or access issue without sharing a secret?"
)
HISTORY_PLACEHOLDER = '[Credential-related request withheld from model context]'

_SECRET = re.compile(
    r"\b(?:passwords?|passcodes?|(?:api|private|access|secret)\s*keys?|client\s*secrets?|"
    r"(?:access|refresh|bearer|setup)\s*tokens?|session\s*cookies?|"
    r"one[ -]time\s*(?:codes?|passwords?)|otps?|(?:recovery|backup)\s*codes?|"
    r"temporary\s+access\s+pass(?:es)?|credentials?|creds|login\s+details)\b"
)
_READ = re.compile(r"\b(?:show|tell|reveal|give|send|share|retrieve|get|find|extract|dump|print|display|expose|use|provide|disclose|fetch|export|list|return|read|copy)\b")
_HELP_SUFFIX = re.compile(r"^\s+(?:polic(?:y|ies)|requirements?|reset|setup|rotation|security|manager|length|expir\w*|lifetime|validity|strength|recovery|management|protection)\b")
_HELP_PREFIX = re.compile(r"\b(?:how\s+(?:to|can|do|should)|steps?\s+to|instructions?\s+(?:to|for))\b.{0,60}\b(?:reset|chang\w*|recover|rotat\w*|creat\w*|generat\w*|request|protect|manag\w*)\b")
_PRONOUN = re.compile(r"\b(?:show|reveal|give|send|share|retrieve|dump|print|display|expose|provide|disclose|fetch|export|list|return|read|copy)\b\s+(?:me\s+)?(?:it|them|that|the\s+(?:actual\s+)?value|the\s+old\s+key)\b")
_NOT_VALUES = {'not','wrong','incorrect','invalid','expired','missing','blocked','locked','forgotten','unknown','required','too','weak','strong','changing','reset','a','the'}
_SHARING_POLICY = re.compile(r'^(?:can|could|should|may)\s+i\s+(give|share|tell|send)\b')
_STAFF_POLICY = re.compile(r'^(?:can|could|should)\s+(?:it(?:\s+staff)?|the\s+helpdesk|support\s+staff)\s+(tell|retrieve|see|know)\b')


def _policy_discussion(prefix, reads):
    """Keep questions about third-party sharing rules distinct from 'tell me it'."""
    sharing = _SHARING_POLICY.match(prefix.strip())
    staff = _STAFF_POLICY.match(prefix.strip())
    match = sharing or staff
    if not match or (reads and reads[-1].group() != match.group(1)):
        return False
    return bool(staff or re.search(r'\b(?:manager|helpdesk|support|it staff)\b',prefix))


def _normalise(text):
    return re.sub(r'[\u200b-\u200f\ufeff]', '', unicodedata.normalize('NFKC', text)).casefold().replace('’', "'").replace('_', ' ')


def requires_credential_refusal(question, previous_blocked=False):
    text = _normalise(question)
    secrets = list(_SECRET.finditer(text))
    direct_secrets = [match for match in secrets if not _HELP_SUFFIX.match(text[match.end():])]
    if (previous_blocked or direct_secrets) and _PRONOUN.search(text):
        return True
    for secret in secrets:
        suffix = text[secret.end():]
        offered = re.match(r'''\s*["']?\s*(?:is\b|=|:)\s*["']?([^\s]+)''', suffix)
        value = offered.group(1).strip('"\'.,!?') if offered else ''
        if value and value not in _NOT_VALUES:
            return True
        if _HELP_SUFFIX.match(suffix):
            continue
        prefix = re.split(r'[?;\n.!]',text[:secret.start()])[-1][-160:]
        if re.search(r'\bhow\s+(?:(?:do|can|should)\s+i|to)\s+use\s+(?:(?:my|a|an|the)\s+)?$', prefix):
            continue
        reads = list(_READ.finditer(prefix))
        if _policy_discussion(prefix,reads):
            continue
        if reads:
            between = prefix[reads[-1].end():]
            if not _HELP_PREFIX.search(between) and not re.search(r'\b(?:how long|how often|why)\b', between):
                return True
        if re.search(r"\bwhat(?:'s| is| are)\b", prefix) and not re.search(r"\bwhat(?:'s| is)\s+an?\s*$", prefix):
            return True
    return False


def safe_history_content(message):
    text = str(message.content)
    if message.type == 'human' and requires_credential_refusal(text):
        return HISTORY_PLACEHOLDER
    return text
