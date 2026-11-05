import os
from dotenv import load_dotenv
from pinecone import Pinecone


load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
index_name= os.getenv("PINECONE_INDEX_NAME", "it-support-knowledge")

if not api_key:
    raise ValueError("PINECONE_API_KEY is missing from .env")

pc = Pinecone(api_key=api_key)

existing_indexes = [
    index.name for index in pc.indexes.list()
]

if index_name in existing_indexes:
    print(f"{index_name} already exists!")
else:
    print("Creating Pinecone indexes...")

    pc.create_index_for_model(
        name=index_name, #Name of  Pinecone index
        cloud="aws", #Cloud provider hosting the index
        region="us-east-1", #Cloud region where the index is hosted
        embed = {
            "model":"llama-text-embed-v2", #Embedding model used by Pinecone
            "field_map":{"text":"text"} #Maps the input text field to the embedding model's expected text field
        }
    )

    print("Index creation requested.")

description = pc.describe_index(index_name)

print("Name:", description.name)
print("Host:", description.host)
print("Ready:", description.status.ready)
print("Schema fields:", description.schema.fields)








