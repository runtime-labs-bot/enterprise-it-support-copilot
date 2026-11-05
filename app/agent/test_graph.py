
from app.agent.graph import app


def run_test(question: str):

    print("\n" + "=" * 60)
    print("EMPLOYEE QUESTION:", question)
    print("=" * 60)

    result = app.invoke({
        "question": question
    })

    print("\nWORKFLOW STATUS:")
    print(result["status"])

    print("\nFINAL ANSWER:")
    print(result["answer"])

    print("\nSOURCES:")
    for source in result.get("sources", []):
        print(source)


if __name__ == "__main__":

    # Test 1: Relevant internal IT question
    run_test(
        "How do I recover MFA access after losing my phone?"
    )

    # Test 2: Question not covered by the IT knowledge base
    run_test(
        "What is the company's maternity leave policy?"
    )

    run_test(
        "How do I troubleshoot DNS resolution errors on Windows?",
        
    )

    run_test(
        "What causes a blue screen error in Windows?"
    )

