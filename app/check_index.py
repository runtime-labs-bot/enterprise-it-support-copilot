
import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY")
)

index_name = os.getenv(
    "PINECONE_INDEX_NAME",
    "it-support-knowledge"
)

index = pc.Index(name=index_name)

stats = index.describe_index_stats()

print("Pinecone index:", index_name)
print("Vector count:", stats.total_vector_count)
print("Index accessible successfully!")
