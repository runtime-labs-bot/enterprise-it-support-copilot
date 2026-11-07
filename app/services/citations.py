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


def validate_generated_answer(answer, source_count, finish_reason):
    references = citation_numbers(answer or '')
    return bool(answer and answer.strip() and references and references <= set(range(1, source_count + 1)) and finish_reason == 'stop')


def unsourced_answer():
    return {'answer': "I couldn't produce a complete answer with valid supporting citations. Could you share the exact error or clarify the issue so I can try a more focused lookup?", 'sources': [], 'grounded': False}
