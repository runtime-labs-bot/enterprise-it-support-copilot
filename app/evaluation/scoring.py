"""Pure scoring functions: no providers, credentials, or application state."""
import re
from pathlib import PurePosixPath
from app.services.citations import citation_numbers

DOCUMENT_ID_MAP = {
    "password_reset_and_unlock": "KB-IAM-0011",
    "mfa_enrollment_and_recovery": "KB-IAM-0015",
    "vpn_troubleshooting": "KB-NET-0042",
    "software_requests_and_installation": "KB-SW-0008",
}
GROUPS = ("policy_citations", "clarification", "ticket_creation", "ownership", "closure_permissions", "failure_handling", "scope")


def document_id(value):
    if not isinstance(value, str):
        return None
    name = PurePosixPath(value.replace("\\", "/")).stem
    return DOCUMENT_ID_MAP.get(name, name)


def score_knowledge(case, state):
    answer = state.get("answer", "")
    chunks = state.get("retrieved_chunks", [])
    sources = state.get("sources", [])
    expected = set(case.get("expected_document_ids", []))
    retrieved = {document_id(chunk.get("document_id")) for chunk in chunks}
    chunk_ids = {chunk.get("id"): document_id(chunk.get("document_id")) for chunk in chunks if chunk.get("id")}
    referenced = citation_numbers(answer)
    by_id = {source.get("source_id"): source for source in sources if type(source.get("source_id")) is int}
    valid = set()
    cited_docs = set()
    web_urls = {row.get("url") for row in state.get("web_results", [])}
    for number in referenced:
        source = by_id.get(number)
        if source is None:
            continue
        chunk_id = source.get("chunk_id")
        if chunk_id and chunk_id in chunk_ids:
            valid.add(number)
            cited_docs.add(chunk_ids[chunk_id])
        elif source.get("url") and source["url"] in web_urls and source["url"].startswith(("https://", "http://")):
            valid.add(number)
    settings = case.get("evaluation", {})
    checks = {"status": state.get("status") == case["expected_status"], "nonempty_answer": bool(answer.strip())}
    category = (state.get("classification") or {}).get("category")
    # The knowledge graph skips classification when retrieval is sufficient.
    if category is not None:
        checks["category"] = category == case["expected_category"]
    if expected:
        checks["retrieved_expected_documents"] = expected <= retrieved
    if settings.get("require_citations", case["expected_status"] in {"answered", "answered_web"}):
        checks["citation_labels_present"] = bool(referenced)
        checks["citations_resolve_to_supplied_context"] = bool(referenced) and referenced == valid and len(by_id) == len(sources)
        if expected:
            checks["expected_documents_actually_cited"] = expected <= cited_docs
    if settings.get("require_clarification"):
        checks["asks_for_clarification"] = bool(re.search(r"\b(could|can|please|what|which|share|provide|clarify)\b", answer, re.I) and "?" in answer)
        checks["no_unsupported_sources"] = not sources
    for keyword in case.get("expected_keywords", []):
        words = {"2": "two", "5": "five", "7": "seven", "8": "eight", "10": "ten", "12": "twelve", "14": "fourteen", "30": "thirty", "180": "one hundred (?:and )?eighty"}
        pattern = "(?:" + re.escape(keyword) + "|" + words[keyword] + ")" if keyword in words else re.escape(keyword)
        checks["keyword:" + keyword] = bool(re.search(r"(?<!\w)" + pattern + r"(?!\w)", answer, re.I))
    for pattern in settings.get("required_patterns", []):
        checks["required_pattern:" + pattern] = bool(re.search(pattern, answer, re.I))
    return checks, {
        "actual_status": state.get("status", "unknown"),
        "retrieved_document_ids": sorted(retrieved - {None}),
        "cited_document_ids": sorted(cited_docs - {None}),
        "category_checked": category is not None,
        "document_recall": len(expected & retrieved) / len(expected) if expected else None,
        "cited_document_recall": len(expected & cited_docs) / len(expected) if expected else None,
    }


def summarize(rows, fail_under=1.0):
    total = len(rows)
    passed = sum(row["status"] == "passed" for row in rows)
    critical = [row["id"] for row in rows if row.get("critical") and row["status"] != "passed"]
    errors = sum(row["status"] == "error" for row in rows)
    skipped = sum(row["status"] == "skipped" for row in rows)
    return {
        "total": total, "passed": passed,
        "failed": sum(row["status"] == "failed" for row in rows),
        "errors": errors,
        "skipped": skipped,
        "pass_rate": passed / total if total else None,
        "critical_failures": critical,
        "gate_passed": bool(total) and not critical and not errors and not skipped and passed / total >= fail_under,
    }
