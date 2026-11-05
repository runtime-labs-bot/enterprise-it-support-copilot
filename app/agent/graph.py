from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState
from app.retrieval.search_knowledge import search_knowledge
from app.agent.retrieval_grader import grade_retrieval
from app.services.answer_generator import generate_answer
from app.agent.question_classifier import classify_question
from app.services.web_search import search_web 
from app.agent.web_result_grader import grade_web_results
from app.services.web_answer_generator import generate_web_answer



#Node1 retrieve documents from pinecone


def retrieve_documents(state: AgentState) -> dict:
    question = state["question"]

    # Focused queries for common IT support topics
    additional_queries = [
        "What company policy applies to the issue described?",
        "What troubleshooting steps or approved procedures apply?"
    ]

    retrieved_chunks = search_knowledge(
        question,
        top_k=5,
        additional_queries=additional_queries
    )

    print("Total retrieved chunks:", len(retrieved_chunks))

    return {
        "retrieved_chunks": retrieved_chunks
    }


#Node2 grade the retrieved documents

def grade_documents(state:AgentState)->dict:
    question = state["question"]
    retrieved_chunks = state["retrieved_chunks"]
    grading_result = grade_retrieval(
        question,
        retrieved_chunks
    )

    return {
        "grading_result":grading_result
    }

def classify_question_node(state:AgentState):
    print("Executing question classification node...")
    question=state["question"]
    classification=classify_question(question)
    print("Question Category:",classification["category"])
    print("Classification reason:", classification["reason"])

    return {
        "classification":classification
    }

def web_search_node(state:AgentState):
    print("Executing web search node...")

    question = state["question"]
    web_results = search_web(question,max_results=5)
    print("Number of web results:",len(web_results))

    return {
        "web_results":web_results
    }

def grade_web_results_node(state: AgentState):
    print("Executing web result grading node...")

    question = state["question"]
    web_results = state.get("web_results", [])

    grading_result = grade_web_results(
        question,
        web_results
    )

    print("Web results relevant:", grading_result["relevant"])
    print("Grading reason:", grading_result["reason"])

    return {
        "web_grading_result": grading_result
    }

def web_generate_node(state: AgentState):

    result = generate_web_answer(
        question=state["question"],
        web_results=state["web_results"]
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "status": "answered_web"
    }

def route_after_web_grading(state:AgentState):
    grading_result=state["web_grading_result"]

    if grading_result["relevant"]:
        return "web_generate"

    return "fallback"

##ROUTER decides what happens after classification

def route_after_classification(state: AgentState):
    category = state["classification"]["category"]

    if category == "general_technical":
        return "web_search"

    elif category == "internal_company":
        return "fallback"

    elif category == "other":
        return "out_of_scope"

    return "fallback"

#ROUTER decides what happens after grading

def route_after_grading(state:AgentState)->str:
    grading_result=state["grading_result"]
    if grading_result["relevant"]:
        return "generate"

    return "fallback"

#Node3 Generate answer from the retrieved documents

def generate_response(state: AgentState) -> dict:

    print("\nExecuting answer generation node...")

    result = generate_answer(
        state["question"],
        state["retrieved_chunks"]
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "status": "answered"
    }

#Node4 Handle insufficient internal knowledge

def handle_insufficient_context(state:AgentState)->dict:
    grading_result=state["grading_result"]

    answer = (
        "I could not find sufficiently relevant information "
        "in the internal IT knowledge base to answer your question.\n\n"
        f"Reason: {grading_result.get('reason', 'Insufficient context')}\n\n"
        f"Missing information: "
        f"{grading_result.get('missing_information', 'Not specified')}"
    )

    return {
        "answer":answer,
        "sources":[],
        "status":"insufficient_context"
    }

# Handle questions outside the IT support domain

def handle_out_of_scope(state: AgentState) -> dict:

    answer = (
        "I'm an Enterprise IT Support Copilot designed to help "
        "with company IT-related questions.\n\n"
        "Your question appears to be outside my supported scope. "
        "Please ask me something related to IT support, "
        "such as VPN, password resets, MFA, or software installation."
    )

    return {
        "answer": answer,
        "sources": [],
        "status": "out_of_scope"
    }

#now build the graph

workflow = StateGraph(AgentState)

workflow.add_node("retrieve",retrieve_documents)
workflow.add_node("grade",grade_documents)
workflow.add_node("classify", classify_question_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("grade_web", grade_web_results_node)
workflow.add_node("generate",generate_response)
workflow.add_node("web_generate", web_generate_node)
workflow.add_node("fallback",handle_insufficient_context)
workflow.add_node("out_of_scope", handle_out_of_scope)

#workflow sequence
workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", "grade")

## Conditional routing after grading
workflow.add_conditional_edges(
    "grade",
    route_after_grading,
    {
        "generate":"generate",
        "fallback":"classify"
    }
)

workflow.add_conditional_edges(
    "classify",
    route_after_classification,
    {
        "web_search":"web_search",
        "fallback":"fallback",
        "out_of_scope": "out_of_scope"
    }
)

workflow.add_conditional_edges(
    "grade_web",
    route_after_web_grading,
    {
        "web_generate": "web_generate",  
        "fallback": "fallback"
    }
)



workflow.add_edge("generate",END)
workflow.add_edge("fallback",END)
workflow.add_edge("web_search", "grade_web")
workflow.add_edge("web_generate", END)
workflow.add_edge("out_of_scope", END)

app=workflow.compile()




