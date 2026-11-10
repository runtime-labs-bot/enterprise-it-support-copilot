"""Render attribution explicitly supplied by the model; never assign sources."""
import json
import re


def output_instructions(source_count):
    return (
        '\nNever request, reveal, or repeat secret credentials. Explain recovery or '
        'security policy without asking the user to paste passwords, API keys, or codes. '
        '\nOUTPUT CONTRACT:\nReturn only a JSON object with a claims array. '
        'Each claim must have exactly text (a nonempty string) and source_ids '
        '(a nonempty array of integer IDs from the supplied sources). '
        'Example shape: {"claims":[{"text":"A supported statement.","source_ids":[1]}]}. '
        f'Available IDs are 1 through {source_count}. '
        'Use a few concise claims. Put Markdown inside text, but no citation labels: '
        'the application renders those from source_ids. Include only claims supported '
        'by the referenced source content. Do not add a source just to increase coverage. '
        'When distinct policies apply, explain the relevant constraints and attribute '
        'each to its actual supporting source. Do not invent facts to fill gaps. '
        'If no supported claim is possible, return {"claims":[]}.'
    )


def render_cited_output(raw, source_count):
    """Keep already cited Markdown compatible; structured output must validate whole."""
    stripped = raw.lstrip()
    structured = stripped.startswith('{') or re.match(r'^\[\s*(?:[\[{\"]|true\b|false\b|null\b|-?\d|\])', stripped)
    if not structured:
        return raw, {'mode':'inline','error':None}
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return '', {'mode':'structured','error':'invalid_json'}
    if not isinstance(payload,dict) or set(payload) != {'claims'} or not isinstance(payload['claims'],list):
        return '', {'mode':'structured','error':'invalid_claims_shape'}
    if not payload['claims']:
        return '', {'mode':'structured','error':'no_supported_claims','claim_count':0}
    rendered = []
    for claim in payload['claims']:
        if not isinstance(claim,dict) or set(claim) != {'text','source_ids'} or not isinstance(claim['text'],str) or not claim['text'].strip():
            return '', {'mode':'structured','error':'invalid_claim'}
        ids = claim['source_ids']
        if not isinstance(ids,list) or not ids or any(type(number) is not int or not 1 <= number <= source_count for number in ids):
            return '', {'mode':'structured','error':'invalid_source_ids'}
        # Render only IDs declared on this claim, never other retrieved sources.
        labels = ' '.join(f'[Source {number}]' for number in sorted(set(ids)))
        rendered.append(claim['text'].strip()+' '+labels)
    return '\n\n'.join(rendered), {'mode':'structured','error':None,'claim_count':len(rendered)}
