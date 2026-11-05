import os
from dotenv import load_dotenv
from pinecone import Pinecone

#It takes the chunks from your chunking step, sends them to Pinecone, and Pinecone turns each one into a vector and stores it. When it finishes, your knowledge base is searchable.
from app.ingestion.chunk_documents import load_and_chunk_documents

load_dotenv()

api_key= os.getenv("PINECONE_API_KEY")

index_name = os.getenv(
    "PINECONE_INDEX_NAME",
    "it-support-knowledge"
)

if not api_key:
    raise ValueError("PINECONE_API_KEY is missing from .env")

pc = Pinecone(api_key=api_key)

index=pc.Index(name=index_name)

chunks = load_and_chunk_documents()

records = []

for chunk in chunks:
    
    record={
        "_id": chunk["chunk_id"],
        "text": chunk["text"],
        "source": chunk["source"],
        "document_id": chunk["document_id"],
        "chunk_number": chunk["chunk_number"],
        "start_index": chunk["start_index"],
        "section": chunk["section"]
    }

    records.append(record)

namespace = "meridian-logistics"
batch_size = 50

print("\nStarting Pinecone ingestion...")

for start in range(0,len(records),batch_size):
    batch=records[start:start + batch_size]
#actual Pinecone upload operation
    index.upsert_records(namespace=namespace,records=batch)

    print(
        f"Uploaded {min(start + batch_size, len(records))}"
        f"/{len(records)} records"
    )

print("\nDocument Ingestion Completed!")

stats = index.describe_index_stats()

print("Total vectors:", stats.total_vector_count)
print("Namespaces:", stats.namespaces)












