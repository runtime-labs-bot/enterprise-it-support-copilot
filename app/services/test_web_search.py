
from app.services.web_search import search_web


if __name__ == "__main__":

    question = "How do I troubleshoot DNS resolution errors on Windows?"

    print("\nSearching the public web...")

    results = search_web(question, max_results=5)

    
    print("TAVILY SEARCH RESULTS")
    

    for i, result in enumerate(results, start=1):

        print(f"\nResult {i}")
        print("Title:", result["title"])
        print("URL:", result["url"])
        print("Content:", result["content"][:500])
        print("Score:", result["score"])
