
import json
from pathlib import Path

from app.retrieval.search_knowledge import search_knowledge

# Project paths
BASE_DIR = Path(__file__).resolve().parents[2]
TEST_FILE = BASE_DIR / "evals" / "test_cases.json"
RESULT_FILE = BASE_DIR / "evals" / "retrieval_results.json"

# Convert Pinecone document IDs into knowledge-base IDs
DOCUMENT_ID_MAP = {
    "password_reset_and_unlock": "KB-IAM-0011",
    "mfa_enrollment_and_recovery": "KB-IAM-0015",
    "vpn_troubleshooting": "KB-NET-0042",
    "software_requests_and_installation": "KB-SW-0008",
}


def load_test_cases():
    with open(TEST_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def evaluate_retrieval(test_case):
    question = test_case["question"]

    print(f"\nRunning {test_case['id']}: {question}")

    try:
        # Directly query Pinecone; no LangGraph or Groq calls
        retrieved_chunks = search_knowledge(question, top_k=5)

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
            recall = (
                len(expected_document_ids & retrieved_document_ids)
                / len(expected_document_ids)
            )
        else:
            recall = None

        return {
            "id": test_case["id"],
            "question": question,
            "expected_document_ids": sorted(expected_document_ids),
            "retrieved_document_ids": sorted(retrieved_document_ids),
            "document_recall": recall,
            "retrieved_chunk_count": len(retrieved_chunks),
            "error": None
        }

    except Exception as error:
        return {
            "id": test_case["id"],
            "question": question,
            "error": str(error)
        }


def main():
    test_cases = load_test_cases()

    results = []

    for test_case in test_cases:
        result = evaluate_retrieval(test_case)
        results.append(result)

        if result.get("error"):
            print("ERROR:", result["error"])
        elif result["document_recall"] is not None:
            print(
                "Document recall:",
                f"{result['document_recall']:.2%}"
            )
        else:
            print("No expected documents specified.")

    valid_results = [
        r for r in results
        if not r.get("error")
        and r["document_recall"] is not None
    ]

    average_recall = (
        sum(r["document_recall"] for r in valid_results)
        / len(valid_results)
        if valid_results else None
    )

    summary = {
        "total_cases": len(test_cases),
        "successful_cases": len(results) - sum(
            1 for r in results if r.get("error")
        ),
        "failed_cases": sum(
            1 for r in results if r.get("error")
        ),
        "cases_with_expected_documents": len(valid_results),
        "average_document_recall": average_recall
    }

    output = {
        "summary": summary,
        "results": results
    }

    with open(RESULT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    print("\n========== RETRIEVAL EVALUATION ==========")
    print(json.dumps(summary, indent=4))
    print(f"\nResults saved to: {RESULT_FILE}")


if __name__ == "__main__":
    main()
