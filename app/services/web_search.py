import os

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise ValueError("TAVILY_API_KEY is missing from .env")

client = TavilyClient(api_key=api_key)

def search_web (question:str,max_results:int=5)->list[dict]:
    """
    Search the public web for general technical information.
    """

    if not question.strip():
        raise ValueError("Search question cannot be empty.")

    response = client.search(
        query=question,
        search_depth="basic",
        max_results=max_results,
        include_answer=False
    )

    results=[]

    for item in response.get("results",[]):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "score": item.get("score", 0.0)
        })


    return results    



