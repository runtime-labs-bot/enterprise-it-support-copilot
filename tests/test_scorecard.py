from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.evaluation.scoring import citation_numbers, score_knowledge, summarize
from app.evaluation.scorecard import catalog, choose_knowledge, compare_baseline, fingerprint, markdown, merge_reports, report, row, run_checks, run_knowledge
from app.evaluation.knowledge_worker import run as run_live_case

CASE = {"id": "test-policy", "profile": "knowledge", "group": "policy_citations", "critical": False, "question": "How do I reset my password?", "expected_status": "answered", "expected_category": "internal_company", "expected_document_ids": ["KB-IAM-0011"], "evaluation": {"require_citations": True}}
STATE = {"status": "answered", "answer": "Use the company reset process [Source 1].", "retrieved_chunks": [{"id": "chunk-a", "document_id": "password_reset_and_unlock"}], "sources": [{"source_id": 1, "document": "password_reset_and_unlock.md", "chunk_id": "chunk-a"}]}


class KnowledgeScoringTests(unittest.TestCase):
    def test_ascii_and_unicode_citations_resolve_to_the_same_supplied_source(self):
        for label in ("[Source 1]", "【Source 1】"):
            with self.subTest(label=label):
                checks, observed = score_knowledge(CASE, {**STATE, "answer": "Reset it " + label})
                self.assertTrue(all(checks.values()))
                self.assertEqual(observed["cited_document_ids"], ["KB-IAM-0011"])
        self.assertEqual(citation_numbers("【Sources 1, 2】 [Source 3] 【Source 4 and 5】"), {1, 2, 3, 4, 5})

    def test_both_citation_styles_keep_source_validation_and_reject_malformed_labels(self):
        for label in ("[Source 99]", "【Source 99】"):
            checks, _ = score_knowledge(CASE, {**STATE, "answer": label})
            self.assertTrue(checks["citation_labels_present"])
            self.assertFalse(checks["citations_resolve_to_supplied_context"])
        for label in ("[Source 1]", "【Source 1】"):
            checks, _ = score_knowledge(CASE, {**STATE, "answer": label, "sources": [{"source_id": 1, "chunk_id": "fabricated"}]})
            self.assertFalse(checks["citations_resolve_to_supplied_context"])
        for label in ("[Source 1】", "【Source 1]", "【Source 1 garbage】", "Source 1", "【1】"):
            with self.subTest(label=label):
                self.assertEqual(citation_numbers(label), set())

    def test_retrieval_alone_does_not_pass_citations(self):
        checks, observed = score_knowledge(CASE, STATE)
        self.assertTrue(all(checks.values()))
        self.assertEqual(observed["cited_document_recall"], 1)
        no_citation = {**STATE, "answer": "Use the company reset process."}
        checks, observed = score_knowledge(CASE, no_citation)
        self.assertTrue(checks["retrieved_expected_documents"])
        self.assertFalse(checks["citation_labels_present"])
        self.assertFalse(checks["expected_documents_actually_cited"])
        self.assertEqual(observed["cited_document_recall"], 0)

    def test_fabricated_labels_chunks_and_duplicate_source_ids_fail(self):
        states = [
            {**STATE, "answer": "Reset it [Source 99]."},
            {**STATE, "sources": [{"source_id": 1, "chunk_id": "not-supplied"}]},
            {**STATE, "sources": STATE["sources"] * 2},
        ]
        for state in states:
            checks, _ = score_knowledge(CASE, state)
            self.assertFalse(checks["citations_resolve_to_supplied_context"])

    def test_expected_document_must_be_cited_even_if_another_source_is_valid(self):
        state = deepcopy(STATE)
        state["retrieved_chunks"].append({"id": "chunk-b", "document_id": "vpn_troubleshooting"})
        state["sources"] = [{"source_id": 1, "chunk_id": "chunk-b"}]
        checks, _ = score_knowledge(CASE, state)
        self.assertTrue(checks["citations_resolve_to_supplied_context"])
        self.assertFalse(checks["expected_documents_actually_cited"])

    def test_web_citation_requires_a_supplied_url(self):
        case = {**CASE, "expected_status": "answered_web", "expected_document_ids": []}
        state = {"status": "answered_web", "answer": "Read this [Source 1].", "sources": [{"source_id": 1, "url": "https://vendor.example/help"}], "web_results": [{"url": "https://vendor.example/help"}]}
        self.assertTrue(all(score_knowledge(case, state)[0].values()))
        state["web_results"] = []
        self.assertFalse(score_knowledge(case, state)[0]["citations_resolve_to_supplied_context"])

    def test_citation_variants_and_numeric_boundaries(self):
        self.assertEqual(citation_numbers("[Sources 1, 2] [Source 3, Source 4] [Source 5 and 6]"), {1, 2, 3, 4, 5, 6})
        case = {**CASE, "expected_keywords": ["5"]}
        self.assertTrue(score_knowledge(case, {**STATE, "answer": "Five attempts [Source 1]."})[0]["keyword:5"])
        self.assertFalse(score_knowledge(case, {**STATE, "answer": "150 attempts [Source 1]."})[0]["keyword:5"])

    def test_uncertainty_requires_a_followup_and_no_sources(self):
        case = {**CASE, "expected_status": "insufficient_context", "expected_document_ids": [], "evaluation": {"require_citations": False, "require_clarification": True}}
        state = {"status": "insufficient_context", "answer": "Could you share the exact problem?", "sources": []}
        self.assertTrue(all(score_knowledge(case, state)[0].values()))
        self.assertFalse(score_knowledge(case, {**state, "answer": "No information available."})[0]["asks_for_clarification"])


class ScorecardGateTests(unittest.TestCase):
    def test_errors_skips_empty_runs_and_critical_failures_never_pass(self):
        self.assertFalse(summarize([])["gate_passed"])
        for status in ("error", "skipped"):
            self.assertFalse(summarize([{"id": "case", "status": status}], fail_under=0)["gate_passed"])
        self.assertFalse(summarize([{"id": "security", "status": "failed", "critical": True}], fail_under=0)["gate_passed"])
        summary = summarize([{"id": "one", "status": "passed"}, {"id": "two", "status": "skipped"}])
        self.assertEqual(summary["pass_rate"], .5)

    def test_baseline_regressions_and_changed_expectations_fail(self):
        before = row(CASE, {"status": "passed"})
        failed = row(CASE, {"status": "failed"})
        baseline = {"results": [before]}
        self.assertEqual(compare_baseline([failed], baseline)["regressions"], [CASE["id"]])
        self.assertFalse(report([failed], fail_under=0, baseline=baseline)["summary"]["gate_passed"])
        changed = row({**CASE, "expected_status": "other"}, {"status": "passed"})
        self.assertFalse(compare_baseline([changed], baseline)["compatible"])
        self.assertFalse(compare_baseline([before], {"results": [before, before]})["gate_passed"])

    def test_report_shows_unrun_areas_without_raw_answer_or_credentials(self):
        result = row(CASE, {"status": "passed", "checks": {"citation_labels_present": True}})
        data = report([result])
        text = markdown(data)
        self.assertIn("Not run", text)
        self.assertIn("not semantic entailment", text)
        self.assertNotIn(STATE["answer"], json.dumps(data))

    def test_manifest_has_unique_ids_and_current_permission_cases(self):
        cases = catalog()
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        self.assertGreaterEqual(sum(case["profile"] == "knowledge" for case in cases), 98)
        self.assertTrue(any("ticket_review" in case.get("test", "") for case in cases))
        self.assertTrue(any("admin_chat" in case.get("test", "") for case in cases))

    def test_default_live_smoke_covers_policy_uncertainty_and_scope(self):
        cases = [case for case in catalog() if case["profile"] == "knowledge"]
        selected = choose_knowledge(cases, 5)
        self.assertTrue({"policy_citations", "clarification", "scope"} <= {case["group"] for case in selected})
        self.assertEqual(choose_knowledge(cases, 2, False), cases[:2])

    def test_merge_preserves_failures_and_rejects_duplicate_or_stale_cases(self):
        other = {**CASE, "id": "second"}
        with TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps({"results": [row(CASE, {"status": "passed"})]}))
            second.write_text(json.dumps({"results": [row(other, {"status": "failed"})]}))
            results = merge_reports([first, second], [CASE, other])
            self.assertEqual(summarize(results)["failed"], 1)
            with self.assertRaises(ValueError):
                merge_reports([first, first], [CASE])
            with self.assertRaises(ValueError):
                merge_reports([first], [{**CASE, "expected_status": "different"}])

    def test_report_cannot_override_catalog_safety_severity(self):
        critical = {**CASE, "critical": True}
        outcome = row(critical, {"status": "failed", "critical": False, "id": "spoofed", "group": "other"})
        self.assertTrue(outcome["critical"])
        self.assertEqual(outcome["id"], CASE["id"])
        self.assertFalse(report([outcome], fail_under=0)["summary"]["gate_passed"])
        self.assertFalse(compare_baseline([outcome], {"results": [{"id": CASE["id"]} ]})["compatible"])


class EvaluationWorkerTests(unittest.TestCase):
    def test_missing_test_outcomes_are_errors_and_not_silent_passes(self):
        case = {"id": "runtime", "profile": "offline", "group": "ownership", "critical": True, "test": "test_missing.test_absent"}
        with patch("app.evaluation.scorecard.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="[]")):
            result = run_checks([case], "offline")
        self.assertEqual(result[0]["status"], "error")
        self.assertEqual(result[0]["error_type"], "MissingTestOutcome")

    def test_provider_limit_skips_remaining_cases_without_changing_denominator(self):
        second = {**CASE, "id": "second"}
        response = SimpleNamespace(returncode=0, stdout=json.dumps({"status": "error", "error_type": "RateLimitError", "provider_limited": True}))
        with patch("app.evaluation.scorecard.subprocess.run", return_value=response) as worker:
            results = run_knowledge([CASE, second])
        self.assertEqual(worker.call_count, 1)
        self.assertEqual([row["status"] for row in results], ["error", "skipped"])
        self.assertEqual(summarize(results)["total"], 2)
        self.assertFalse(summarize(results)["gate_passed"])

    def test_live_timeout_is_a_reported_error(self):
        with patch("app.evaluation.scorecard.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 1)):
            results = run_knowledge([CASE], timeout=1)
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(results[0]["error_type"], "TimeoutExpired")

    def test_live_worker_uses_no_checkpointer_and_saves_only_scores(self):
        with patch("app.agent.graph.workflow.compile") as compile_graph:
            compile_graph.return_value.invoke.return_value = STATE
            result = run_live_case(CASE)
        compile_graph.assert_called_once_with()
        self.assertEqual(result["status"], "passed")
        self.assertNotIn("answer", result)
        self.assertNotIn("retrieved_chunks", result)
