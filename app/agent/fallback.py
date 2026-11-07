"""Deterministic response when company knowledge cannot support an answer."""


def insufficient_context_response(grading_result):
    return {
        "answer": (
            "I could not find sufficiently relevant information in the internal IT "
            "knowledge base to answer your question.\n\n"
            f"Reason: {grading_result.get('reason', 'Insufficient context')}\n\n"
            f"Missing information: {grading_result.get('missing_information', 'Not specified')}\n\n"
            "Could you share more context about what you need help with?"
        ),
        "sources": [],
        "status": "insufficient_context",
    }
