
from app.services.web_search import search_web
from app.agent.web_result_grader import grade_web_results


if __name__ == "__main__":

    question = "How do I troubleshoot DNS resolution errors on Windows?"

    print("\nSearching the public web...")

    web_results = search_web(question, max_results=5)

    print("\nGrading web search results...")

    result = grade_web_results(question, web_results)

    
    print("WEB RESULT GRADER")
   

    print("Relevant:", result["relevant"])
    print("Reason:", result["reason"])
