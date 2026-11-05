
import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")

if not api_key:
    raise ValueError("PINECONE_API_KEY is missing from .env")

pc = Pinecone(api_key=api_key)

print("Successfully connected to Pinecone!")

for index in pc.indexes.list():
    print(index.name)
