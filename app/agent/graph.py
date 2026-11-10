from langgraph.graph import StateGraph, START, END
from app.services.stage_diagnostics import stage

from app.agent.state import AgentState
from app.agent.credential_contract import REFUSAL, requires_credential_refusal, safe_history_content
from app.agent.fallback import insufficient_context_response
from app.agent.meridian import MeridianContext, meridian_node, route_after_meridian
from app.agent.retrieval_grader import grade_retrieval
from app.services.answer_generator import generate_answer
from app.agent.question_classifier import classify_question
from app.services.web_search import search_web 
from app.agent.web_result_grader import grade_web_results
from app.services.web_answer_generator import generate_web_answer
import sqlite3
import os
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AIMessage



#Node1 retrieve documents from pinecone

def save_response(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content=state["answer"], additional_kwargs={
            "sources": state.get("sources", []), "status": state.get("status", "unknown"),
        })]
    }


def credential_boundary(state: AgentState) -> dict:
    blocked = requires_credential_refusal(state['question'], state.get('credential_request_blocked', False))
    if not blocked:
        return {'credential_request_blocked':False}
    return {'credential_request_blocked':True, 'answer':REFUSAL,
            'status':'insufficient_context', 'sources':[], 'retrieved_chunks':[],
            'web_results':[], 'grading_result':{}, 'web_grading_result':{},
            'generation_diagnostics':{}, 'classification':{},
            'meridian_handled':False, 'meridian_tools':[], 'admin_proposal':None}


def route_after_credential_boundary(state):
    return 'save_response' if state.get('credential_request_blocked') else 'meridian'

def get_contextual_question(state: AgentState) -> str:
    messages = state.get("messages", [])

    # Exclude the latest message because question already contains it
    previous_messages = messages[:-1] if messages else []

    # Use the last 4 messages for context
    recent_messages = previous_messages[-4:]

    if not recent_messages:
        return state["question"]

    conversation = []

    for message in recent_messages:
        role = "User" if message.type == "human" else "Assistant"
        conversation.append(f"{role}: {safe_history_content(message)}")

    context = "\n".join(conversation)

    return (
        f"Previous conversation:\n{context}\n\n"
        f"Current question: {state['question']}"
    )

def retrieve_documents(state: AgentState) -> dict:
    with stage('retrieval', provider='pinecone', component='knowledge_base'):
        from app.retrieval.search_knowledge import search_knowledge

        contextual_question = get_contextual_question(state)

        additional_queries = [
            "What company policy applies to the issue described?",
            "What troubleshooting steps or approved procedures apply?"
        ]

        retrieved_chunks = search_knowledge(
            contextual_question,
            top_k=5,
            additional_queries=additional_queries
        )

    print("Total retrieved chunks:", len(retrieved_chunks))

    return {
        "contextual_question": contextual_question,
        "retrieved_chunks": retrieved_chunks
    }

#Node2 grade the retrieved documents

def grade_documents(state:AgentState)->dict:
    question = state.get("contextual_question", state["question"])
    retrieved_chunks = state["retrieved_chunks"]
    with stage('relevance_grading', component='internal', llm=True):
        grading_result = grade_retrieval(
            question,
            retrieved_chunks
        )

    return {
        "grading_result":grading_result
    }

def classify_question_node(state:AgentState):
    print("Executing question classification node...")
    question = state.get("contextual_question", state["question"])
    with stage('classification', component='question_routing', llm=True):
        classification=classify_question(question)
    print("Question Category:",classification["category"])
    print("Classification reason:", classification["reason"])

    return {
        "classification":classification
    }

def web_search_node(state: AgentState):
    print("Executing web search node...")

    # Use current question for web search, not full conversation history
    question = state["question"]

    # Tavily allows a maximum query length of 1500 characters
    question = question[:1400]

    with stage('retrieval', provider='tavily', component='web'):
        web_results = search_web(question, max_results=5)

    print("Number of web results:", len(web_results))

    return {"web_results": web_results}

def grade_web_results_node(state: AgentState):
    print("Executing web result grading node...")

    question = state.get("contextual_question", state["question"])
    web_results = state.get("web_results", [])

    with stage('relevance_grading', component='web', llm=True):
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
    question=state.get("contextual_question", state["question"]),
    web_results=state["web_results"]
)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "status": "answered_web" if result.get('grounded', True) else "insufficient_context",
        "generation_diagnostics": result.get('generation_diagnostics', {}),
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
    state.get("contextual_question", state["question"]),
    state["retrieved_chunks"]
)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "status": "answered" if result.get('grounded', True) else "insufficient_context",
        "generation_diagnostics": result.get('generation_diagnostics', {}),
    }

#Node4 Handle insufficient internal knowledge

def handle_insufficient_context(state:AgentState)->dict:
    return insufficient_context_response(state["grading_result"])

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

workflow = StateGraph(AgentState, context_schema=MeridianContext)

workflow.add_node('credential_boundary', credential_boundary)
workflow.add_node("meridian", meridian_node)
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
workflow.add_edge(START, 'credential_boundary')
workflow.add_conditional_edges('credential_boundary', route_after_credential_boundary,
                              {'save_response':'save_response','meridian':'meridian'})
workflow.add_conditional_edges(
    "meridian", route_after_meridian,
    {"save_response": "save_response", "retrieve": "retrieve"},
)
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



workflow.add_node("save_response", save_response)

workflow.add_edge("generate", "save_response")
workflow.add_edge("fallback", "save_response")
workflow.add_edge("web_generate", "save_response")
workflow.add_edge("out_of_scope", "save_response")

workflow.add_edge("save_response", END)
workflow.add_edge("web_search", "grade_web")

# Create folder for storing conversation checkpoints
_project_root = Path(__file__).resolve().parents[2]
CHECKPOINT_DB_PATH = Path(os.getenv("COPILOT_CHECKPOINT_DB") or _project_root / "data/checkpoints/checkpoints.sqlite").expanduser()
if not CHECKPOINT_DB_PATH.is_absolute():
    CHECKPOINT_DB_PATH = _project_root / CHECKPOINT_DB_PATH
CHECKPOINT_DB_PATH = CHECKPOINT_DB_PATH.resolve()
CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Create SQLite database connection
conn = sqlite3.connect(
    str(CHECKPOINT_DB_PATH),
    check_same_thread=False
)

# Initialize LangGraph checkpointer
checkpointer = SqliteSaver(conn)
checkpointer.setup()

# Compile graph with persistent memory
app = workflow.compile(checkpointer=checkpointer)




