from app.services.web_search import search_web
from app.services.web_answer_generator import generate_web_answer


def run_test(question: str):

   
    print("QUESTION:", question)
    

    # Step 1: Search the public web
    web_results = search_web(question, max_results=5)

    print("\nWEB RESULTS:", len(web_results))

    # Step 2: Generate answer using web results
    result = generate_web_answer(
        question,
        web_results
    )

    print("\nGENERATED ANSWER:")
    print(result["answer"])

    print("\nSOURCES:")

    for source in result["sources"]:
        print(source)


if __name__ == "__main__":

    run_test(
        "How do I troubleshoot DNS resolution errors on Windows?"
    )