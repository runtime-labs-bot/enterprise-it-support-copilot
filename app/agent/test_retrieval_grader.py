
from app.retrieval.search_knowledge import search_knowledge
from app.agent.retrieval_grader import grade_retrieval


if __name__ == "__main__":

    question = "What is the company's maternity leave policy?"

    print("\nRetrieving documents from Pinecone...")

    retrieved_chunks = search_knowledge(question, top_k=5)

    print("\nGrading retrieved documents...")

    result = grade_retrieval(question, retrieved_chunks)

    print("\n" + "=" * 50)
    print("RETRIEVAL GRADER RESULT")
    print("=" * 50)

    print("Relevant:", result["relevant"])
    print("Reason:", result["reason"])
    print("Missing information:", result["missing_information"])


