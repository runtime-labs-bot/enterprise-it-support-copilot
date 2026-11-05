
from app.retrieval.search_knowledge import search_knowledge
from app.services.answer_generator import generate_answer


if __name__ == "__main__":

    question = "How do I recover MFA access after losing my phone?"

    print("\nSearching internal knowledge base...")

    retrieved_chunks = search_knowledge(
        question,
        top_k=5
    )

    print("\nGenerating answer using Groq...")

    result = generate_answer(
        question,
        retrieved_chunks
    )

    print("\n" + "=" * 60)
    print("GENERATED ANSWER")
    print("=" * 60)

    print(result["answer"])

    print("\n" + "=" * 60)
    print("SOURCES")
    print("=" * 60)

    for source in result["sources"]:
        print(source)

