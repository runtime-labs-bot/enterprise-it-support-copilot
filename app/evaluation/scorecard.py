"""Reproducible scorecard for runtime contracts, backend permissions and live RAG."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from app.evaluation.scoring import GROUPS, summarize

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("offline", "backend", "knowledge")
SMOKE_IDS = ("tc-001", "tc-005", "tc-015", "tc-017", "tc-022")


def fingerprint(case):
    return hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def catalog(root=ROOT):
    workflows = json.loads((root / "evals/workflow_cases.json").read_text(encoding="utf-8"))
    knowledge = json.loads((root / "evals/test_cases.json").read_text(encoding="utf-8"))
    cases = list(workflows)
    for case in knowledge:
        settings = case.get("evaluation", {})
        cases.append({**case, "profile": "knowledge", "group": settings.get("group", "policy_citations"), "critical": settings.get("critical", False)})
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evaluation IDs")
    tests = [(case["profile"], case["test"]) for case in workflows]
    if len(tests) != len(set(tests)):
        raise ValueError("Do not count the same test twice in one profile")
    for case in cases:
        if case["profile"] not in PROFILES or case["group"] not in GROUPS or type(case["critical"]) is not bool:
            raise ValueError("Invalid profile/group/critical flag")
        if case["profile"] != "knowledge" and not case.get("test"):
            raise ValueError("Workflow case must name a test")
    return cases


def row(case, result):
    metadata = {}
    if case["profile"] == "knowledge":
        metadata = {"requires_citations": case.get("evaluation", {}).get("require_citations", case["expected_status"] in {"answered", "answered_web"}), "requires_clarification": case.get("evaluation", {}).get("require_clarification", False), "expected_document_ids": case.get("expected_document_ids", [])}
    return {**result, "id": case["id"], "profile": case["profile"], "group": case["group"], "critical": case["critical"], "expectation_hash": fingerprint(case), **metadata}


def choose_knowledge(cases, limit, prioritize_smoke=True):
    if prioritize_smoke:
        order = {name: index for index, name in enumerate(SMOKE_IDS)}
        cases = sorted(cases, key=lambda case: order.get(case["id"], len(order)))
    return cases[:limit]


def run_checks(cases, profile, timeout=180):
    if not cases:
        return []
    cwd, executable = ROOT, sys.executable
    if profile == "backend":
        from dotenv import load_dotenv
        from app.agent.meridian import meridian_installation
        load_dotenv(ROOT / ".env")
        cwd, executable = meridian_installation()
    env = os.environ.copy()
    if profile == "offline":
        env.update({"SCORECARD_OFFLINE": "1", "GROQ_API_KEY": "offline-scorecard-placeholder", "TAVILY_API_KEY": "offline-scorecard-placeholder", "PINECONE_API_KEY": "offline-scorecard-placeholder"})
    try:
        process = subprocess.run([str(executable), "-B", str(ROOT / "scripts/run_scorecard_checks.py")], input=json.dumps([case["test"] for case in cases]), cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        if process.returncode:
            raise RuntimeError("Check worker failed")
        results = json.loads(process.stdout)
        if not isinstance(results, list) or any(not isinstance(result, dict) or result.get("status") not in {"passed", "failed", "error", "skipped"} for result in results):
            raise ValueError("Invalid check outcome")
        by_test = {result["test"]: result for result in results}
        return [row(case, by_test.get(case["test"], {"status": "error", "error_type": "MissingTestOutcome"})) for case in cases]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        return [row(case, {"status": "error", "error_type": type(error).__name__}) for case in cases]


def run_knowledge(cases, timeout=120, delay=0):
    results = []
    limited = False
    for case in cases:
        if limited:
            results.append(row(case, {"status": "skipped", "reason": "Provider rate/quota limit stopped live evaluation"}))
            continue
        started = time.monotonic()
        try:
            process = subprocess.run([sys.executable, "-B", "-m", "app.evaluation.knowledge_worker"], input=json.dumps(case), cwd=ROOT, capture_output=True, text=True, timeout=timeout)
            if process.returncode:
                raise RuntimeError("Knowledge worker failed")
            result = json.loads(process.stdout)
            if not isinstance(result, dict) or result.get("status") not in {"passed", "failed", "error"}:
                raise ValueError("Invalid knowledge outcome")
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            result = {"status": "error", "error_type": type(error).__name__}
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        results.append(row(case, result))
        print(f"{case['id']}: {result['status']}", flush=True)
        limited = bool(result.get("provider_limited"))
        if delay and case is not cases[-1] and not limited:
            time.sleep(delay)
    return results


def compare_baseline(results, baseline):
    current = {item["id"]: item for item in results}
    try:
        old = {item["id"]: item for item in baseline["results"]}
        if len(old) != len(baseline["results"]):
            raise ValueError("Duplicate baseline IDs")
        if any(item.get("status") not in {"passed", "failed", "error", "skipped"} for item in old.values()):
            raise ValueError("Invalid baseline status")
    except (KeyError, TypeError, ValueError):
        return {"compatible": False, "regressions": [], "gate_passed": False}
    compatible = current.keys() == old.keys() and all(current[key]["expectation_hash"] == old[key].get("expectation_hash") for key in current)
    regressions = sorted(key for key in current if key in old and old[key]["status"] == "passed" and current[key]["status"] != "passed") if compatible else []
    return {"compatible": compatible, "regressions": regressions, "gate_passed": compatible and not regressions}


def report(results, fail_under=1.0, baseline=None):
    summary = summarize(results, fail_under)
    comparison = compare_baseline(results, baseline) if baseline is not None else None
    if comparison and not comparison["gate_passed"]:
        summary["gate_passed"] = False
    return {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary, "profiles_run": sorted({item["profile"] for item in results}),
        "groups": {name: summarize([item for item in results if item["group"] == name], fail_under) for name in GROUPS},
        "baseline_comparison": comparison, "results": results,
    }


def merge_reports(paths, cases):
    known = {case["id"]: case for case in cases}
    merged, seen = [], set()
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data["results"]:
            case = known.get(item["id"])
            if case is None or item["id"] in seen or item.get("expectation_hash") != fingerprint(case) or item.get("profile") != case["profile"]:
                raise ValueError("Reports must contain distinct current cases with unchanged expectations")
            if item.get("status") not in {"passed", "failed", "error", "skipped"}:
                raise ValueError("Invalid merged outcome")
            # Normalize metadata from the catalog while preserving actual outcomes.
            merged.append(row(case, item))
            seen.add(item["id"])
    if not merged:
        raise ValueError("Cannot merge empty reports")
    return merged


def finish(results, args, baseline):
    from dotenv import dotenv_values
    data = report(results, args.fail_under, baseline)
    data["configuration"] = {"profile": "merged" if args.merge else args.profile, "fail_under": args.fail_under}
    if not args.merge:
        data["configuration"].update(knowledge_limit=args.limit, case_timeout_seconds=args.timeout)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = "unknown", None
    model = os.getenv("GROQ_MODEL") or dotenv_values(ROOT / ".env", interpolate=False).get("GROQ_MODEL") or "openai/gpt-oss-20b"
    data["provenance"] = {"git_revision": revision, "working_tree_dirty": dirty, "python": sys.version.split()[0], "model": model}
    if args.merge:
        data["merged_reports"] = [str(path) for path in args.merge]
        data["source_runs"] = [{key: json.loads(path.read_text(encoding="utf-8")).get(key) for key in ("created_at", "profiles_run", "provenance")} for path in args.merge]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(data), encoding="utf-8")
    print(json.dumps(data["summary"], indent=2))
    print("Reports: " + str(args.output.with_suffix(".json")) + " and .md")
    return 0 if data["summary"]["gate_passed"] else 1


def markdown(data):
    summary = data["summary"]
    lines = ["# Copilot evaluation scorecard", "", f"Gate: **{'PASS' if summary['gate_passed'] else 'FAIL'}**", "", "Profiles run: " + ", ".join(data["profiles_run"]), "", "| Area | Passed / requested | Errors | Skipped | Pass rate |", "| --- | --- | --- | --- | --- |"]
    for name, group in data["groups"].items():
        rate = f"{group['pass_rate']:.0%}" if group["pass_rate"] is not None else "Not run"
        lines.append(f"| {name} | {group['passed']} / {group['total']} | {group['errors']} | {group['skipped']} | {rate} |")
    lines += ["", "Critical failures: " + (", ".join(summary["critical_failures"]) or "None"), "", "## Case outcomes", "", "| Case | Evidence | Outcome | Failed checks / error |", "| --- | --- | --- | --- |"]
    for item in data["results"]:
        failed = ", ".join(name for name, passed in item.get("checks", {}).items() if not passed)
        detail = (failed or item.get("error_type") or item.get("reason") or "—").replace("|", "\\|")
        lines.append(f"| {item['id']} | {item['profile']} | {item['status']} | {detail} |")
    if data["baseline_comparison"]:
        lines += ["", "Baseline comparison: " + json.dumps(data["baseline_comparison"])]
    lines += ["", "Offline = scripted runtime/fault checks; backend = real PostgreSQL/API permissions with injected faults where specified; knowledge = live model/retrieval. Not run is not a pass. Citation checks prove source linkage/document coverage, not semantic entailment of every claim. No raw answers, credentials, or retrieved text are saved."]
    return "\n".join(lines) + "\n"


def main(default_profile="offline"):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(*PROFILES, "checks", "all"), default=default_profile)
    parser.add_argument("--ids", help="Comma-separated case IDs")
    parser.add_argument("--tag", help="Filter live knowledge questions by tag")
    parser.add_argument("--limit", type=int, default=5, help="Maximum live knowledge cases; workflows are not limited (default 5)")
    parser.add_argument("--fail-under", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per live case / workflow batch in seconds")
    parser.add_argument("--delay", type=float, default=0, help="Seconds between live cases, at most 60")
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports/latest")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--merge", nargs="+", type=Path, help="Combine distinct existing report outcomes without rerunning checks")
    args = parser.parse_args()
    if args.limit < 1 or args.timeout < 1 or not 0 <= args.fail_under <= 1 or not 0 <= args.delay <= 60:
        parser.error("Require limit/timeout > 0, fail-under in [0,1], and delay in [0,60]")
    if args.merge and (args.ids or args.tag):
        parser.error("Merge combines complete report outcomes; ID/tag filters apply only to new runs")
    try:
        cases = catalog()
    except (OSError, ValueError, KeyError) as error:
        parser.error("Invalid evaluation catalog: " + type(error).__name__)
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            if not isinstance(baseline.get("results"), list):
                raise ValueError("Invalid baseline")
        except (OSError, ValueError, AttributeError):
            parser.error("Cannot read a valid scorecard baseline")
    if args.merge:
        try:
            results = merge_reports(args.merge, cases)
        except (OSError, ValueError, KeyError, TypeError):
            parser.error("Cannot merge reports: require distinct current case IDs and unchanged expectations")
        return finish(results, args, baseline)
    profiles = PROFILES if args.profile == "all" else ("offline", "backend") if args.profile == "checks" else (args.profile,)
    selected = [case for case in cases if case["profile"] in profiles]
    if args.ids:
        requested = set(args.ids.split(","))
        if requested - {case["id"] for case in selected}:
            parser.error("IDs must exist in the selected profile")
        selected = [case for case in selected if case["id"] in requested]
    if args.tag:
        selected = [case for case in selected if args.tag in case.get("tags", [])]
    if not selected:
        parser.error("No evaluation cases selected")
    selected = [case for case in selected if case["profile"] != "knowledge"] + choose_knowledge([case for case in selected if case["profile"] == "knowledge"], args.limit, not args.ids and not args.tag)
    results = []
    for profile in ("offline", "backend"):
        subset = [case for case in selected if case["profile"] == profile]
        if subset:
            print(f"Running {profile}: {len(subset)} checks", flush=True)
            results.extend(run_checks(subset, profile, args.timeout))
    results.extend(run_knowledge([case for case in selected if case["profile"] == "knowledge"], args.timeout, args.delay))
    return finish(results, args, baseline)


if __name__ == "__main__":
    raise SystemExit(main())
