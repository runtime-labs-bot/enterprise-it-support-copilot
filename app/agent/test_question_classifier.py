
from app.agent.question_classifier import classify_question


if __name__ == "__main__":

    questions = [
        "How do I troubleshoot DNS resolution errors on Windows?",

        "What is Meridian Logistics' maternity leave policy?",

        "How do I access Meridian's internal VPN?",

        "What causes a blue screen error in Windows?"
    ]

    for question in questions:

        print("QUESTION:", question)

        result = classify_question(question)

        print("CATEGORY:", result["category"])
        print("REASON:", result["reason"])
        
