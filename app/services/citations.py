"""Recognize supported citation labels without inventing or repairing attribution."""
import re


def citation_numbers(answer):
    references = set()
    for ascii_block, unicode_block in re.findall(r'\[([^\[\]【】]+)\]|【([^\[\]【】]+)】', answer):
        block = ascii_block or unicode_block
        if not re.match(r'Sources?\s+\d', block, re.I):
            continue
        numbers = re.sub(r'\bSources?\s*', '', block, flags=re.I)
        if re.fullmatch(r'\d+(?:(?:\s*[,;&]\s*|\s+and\s+)\d+)*\s*', numbers, re.I):
            references.update(int(number) for number in re.findall(r'\d+', numbers))
    return references


def citation_validation(answer, source_count, finish_reason):
    """Explain rejection without exposing the model's answer or changing the gate."""
    references = citation_numbers(answer or '')
    reasons = []
    if not answer or not answer.strip():
        reasons.append('empty_answer')
    if not references:
        reasons.append('missing_citation_labels')
    if references - set(range(1, source_count + 1)):
        reasons.append('unknown_source_ids')
    if finish_reason != 'stop':
        reasons.append('incomplete_generation')
    return {'accepted': not reasons, 'rejection_reasons': reasons,
            'referenced_source_ids': sorted(references), 'supplied_source_count': source_count}


def validate_generated_answer(answer, source_count, finish_reason):
    return citation_validation(answer, source_count, finish_reason)['accepted']


def unsourced_answer():
    return {'answer': "I couldn't produce a complete answer with valid supporting citations. Could you share the exact error or clarify the issue so I can try a more focused lookup?", 'sources': [], 'grounded': False}
