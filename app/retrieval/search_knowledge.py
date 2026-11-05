
import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX_NAME", "it-support-knowledge")

if not api_key:
    raise ValueError("PINECONE_API_KEY is missing from .env")

pc = Pinecone(api_key=api_key)
index = pc.Index(name=index_name)

NAMESPACE = "meridian-logistics"


def search_knowledge(
    question: str,
    top_k: int = 5,
    additional_queries: list[str] | None = None
):
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    # Always search using the original question
    queries = [question.strip()]

    # Add focused queries, if provided
    if additional_queries:
        for query in additional_queries:
            if query and query.strip() and query.strip() not in queries:
                queries.append(query.strip())

    # Store unique chunks using their Pinecone IDs
    unique_chunks = {}

    total_embedding_tokens = 0

    for query_number, query in enumerate(queries, start=1):

        print(f"\nDEBUG: Search query {query_number}: {query!r}")

        response = index.search(
            namespace=NAMESPACE,
            top_k=top_k,
            inputs={"text": query},
            fields=[
                "text",
                "source",
                "document_id",
                "chunk_number",
                "start_index",
                "section"
            ]
        )

        embedding_tokens = response.usage.embed_total_tokens
        total_embedding_tokens += embedding_tokens

        for hit in response.result.hits:

            chunk = {
                "id": hit.id,
                "score": hit.score,
                "text": hit.fields.get("text", ""),
                "source": hit.fields.get("source", ""),
                "document_id": hit.fields.get("document_id", ""),
                "chunk_number": hit.fields.get("chunk_number", 0),
                "start_index": hit.fields.get("start_index", 0),
                "section": hit.fields.get("section", "")
            }

            chunk_id = chunk["id"]

            # Keep the highest score if the same chunk
            # appears in multiple search results.
            if (
                chunk_id not in unique_chunks
                or chunk["score"] > unique_chunks[chunk_id]["score"]
            ):
                unique_chunks[chunk_id] = chunk

    # Sort unique chunks by relevance score
    results = sorted(
        unique_chunks.values(),
        key=lambda chunk: chunk["score"],
        reverse=True
    )

    print("DEBUG: Total embedding tokens:", total_embedding_tokens)
    print("DEBUG: Search queries executed:", len(queries))
    print("DEBUG: Unique chunks retrieved:", len(results))

    return results


if __name__ == "__main__":

    question = (
        "Can I install a free VPN app to get around my connection problem?"
    )

    focused_queries = [
        "How do I troubleshoot my company VPN connection?",
        "Are personal VPN applications or unapproved software allowed "
        "on company laptops?"
    ]

    results = search_knowledge(
        question,
        top_k=5,
        additional_queries=focused_queries
    )

    for i, result in enumerate(results, start=1):
        print(f"\n--- Result {i} ---")
        print("Score:", round(result["score"], 4))
        print("Document:", result["document_id"])
        print("Source:", result["source"])
        print("Text:", result["text"][:300])




