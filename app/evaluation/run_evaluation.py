
import argparse
import json
from pathlib import Path

from app.agent.graph import app as agent

# Project paths
BASE_DIR = Path(__file__).resolve().parents[2]
TEST_FILE = BASE_DIR / "evals" / "test_cases.json"
RESULT_FILE = BASE_DIR / "evals" / "results.json"

# Map Pinecone document identifiers to knowledge base IDs
DOCUMENT_ID_MAP = {
    "password_reset_and_unlock": "KB-IAM-0011",
    "mfa_enrollment_and_recovery": "KB-IAM-0015",
    "vpn_troubleshooting": "KB-NET-0042",
    "software_requests_and_installation": "KB-SW-0008",
}


def load_test_cases():
    with open(TEST_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def is_daily_quota_error(error):
    """
    Detect errors indicating that the provider's daily token
    quota has been exhausted.
    """
    message = str(error).lower()

    indicators = [
        "tokens per day",
        "daily token",
        "tpd",
        "rate_limit_exceeded",
    ]

    return any(indicator in message for indicator in indicators)


def evaluate_case(test_case):
    question = test_case["question"]

    print(f"\nRunning {test_case['id']}: {question}")

    try:
        result = agent.invoke({"question": question})

        expected_status = test_case["expected_status"]
        actual_status = result.get("status", "unknown")
        status_pass = expected_status == actual_status

        retrieved_chunks = result.get("retrieved_chunks", [])

        retrieved_document_ids = {
            DOCUMENT_ID_MAP.get(
                chunk.get("document_id"),
                chunk.get("document_id")
            )
            for chunk in retrieved_chunks
            if chunk.get("document_id")
        }

        expected_document_ids = set(
            test_case.get("expected_document_ids", [])
        )

        if expected_document_ids:
            document_recall = (
                len(expected_document_ids & retrieved_document_ids)
                / len(expected_document_ids)
            )
        else:
            document_recall = None

        answer = result.get("answer", "")
        expected_keywords = test_case.get("expected_keywords", [])

        missing_keywords = [
            keyword
            for keyword in expected_keywords
            if keyword.lower() not in answer.lower()
        ]

        keyword_pass = len(missing_keywords) == 0

        classification = result.get("classification")
        actual_category = (
            classification.get("category")
            if classification
            else None
        )

        expected_category = test_case["expected_category"]
        category_checked = actual_category is not None

        category_pass = (
            actual_category == expected_category
            if category_checked
            else None
        )

        return {
            "id": test_case["id"],
            "question": question,
            "execution_status": "completed",
            "expected_status": expected_status,
            "actual_status": actual_status,
            "status_pass": status_pass,
            "expected_category": expected_category,
            "actual_category": actual_category,
            "category_checked": category_checked,
            "category_pass": category_pass,
            "expected_document_ids": list(expected_document_ids),
            "retrieved_document_ids": list(retrieved_document_ids),
            "document_recall": document_recall,
            "expected_keywords": expected_keywords,
            "missing_keywords": missing_keywords,
            "keyword_pass": keyword_pass,
            "answer": answer,
            "error": None
        }

    except Exception as error:
        return {
            "id": test_case["id"],
            "question": question,
            "execution_status": "failed",
            "error": str(error),
            "quota_exhausted": is_daily_quota_error(error)
        }


def calculate_summary(results, requested):
    completed = [
        r for r in results
        if r.get("execution_status") == "completed"
    ]

    failed = [
        r for r in results
        if r.get("execution_status") == "failed"
    ]

    skipped = [
        r for r in results
        if r.get("execution_status") == "skipped"
    ]

    category_results = [
        r for r in completed if r["category_checked"]
    ]

    document_results = [
        r for r in completed if r["document_recall"] is not None
    ]

    return {
        "total_cases_requested": requested,
        "completed_cases": len(completed),
        "failed_cases": len(failed),
        "skipped_cases": len(skipped),
        "status_accuracy": (
            sum(r["status_pass"] for r in completed) / len(completed)
            if completed else None
        ),
        "category_accuracy": (
            sum(r["category_pass"] for r in category_results)
            / len(category_results)
            if category_results else None
        ),
        "category_cases_checked": len(category_results),
        "average_document_recall": (
            sum(r["document_recall"] for r in document_results)
            / len(document_results)
            if document_results else None
        ),
        "keyword_pass_rate": (
            sum(r["keyword_pass"] for r in completed) / len(completed)
            if completed else None
        )
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of test cases to run"
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    test_cases = load_test_cases()[:args.limit]

    results = []
    quota_exhausted = False

    for index, test_case in enumerate(test_cases):
        result = evaluate_case(test_case)
        results.append(result)

        if result["execution_status"] == "failed":
            print("ERROR:", result["error"])

            if result.get("quota_exhausted"):
                print(
                    "\nDaily API quota appears exhausted. "
                    "Stopping evaluation to avoid unnecessary requests."
                )
                quota_exhausted = True
                break

        else:
            print(
                "Status:",
                "PASS" if result["status_pass"] else "FAIL"
            )

    # Mark cases that were not executed
    if quota_exhausted:
        next_index = len(results)

        for test_case in test_cases[next_index:]:
            results.append({
                "id": test_case["id"],
                "question": test_case["question"],
                "execution_status": "skipped",
                "reason": "Evaluation stopped because the daily API quota was exhausted."
            })

    summary = calculate_summary(results, len(test_cases))

    output = {
        "summary": summary,
        "quota_exhausted": quota_exhausted,
        "results": results
    }

    # Save results, including partial results
    with open(RESULT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    print("\n========== EVALUATION SUMMARY ==========")
    print(json.dumps(summary, indent=4))

    if quota_exhausted:
        print("\nEvaluation stopped because of API quota exhaustion.")

    print(f"\nDetailed results saved to: {RESULT_FILE}")


if __name__ == "__main__":
    main()


