import hashlib
from fastapi import FastAPI, Header
from app.agent.meridian import MeridianContext
from pydantic import BaseModel
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.agent.graph import app as agent

app = FastAPI(
    title="IT Support Copilot API",
    description="Backend API for our Agentic RAG IT Support Copilot",
    version="1.0.0"
)

class QuestionRequest(BaseModel):
    question: str
    thread_id: str | None = None


@app.get("/")
def home():
    return {"message": "Welcome to IT Support Copilot API"}


@app.post("/ask")
def ask_question(request: QuestionRequest, employee_key: str | None = Header(default=None, alias="X-Meridian-Employee-Key")):

    # Reuse the conversation ID or create a new one
    thread_id = request.thread_id or str(uuid4())
    identity_scope = hashlib.sha256((employee_key or "anonymous").encode()).hexdigest()

    # Pass the question and conversation ID to LangGraph
    result = agent.invoke(
        {
            "question": request.question,
            "messages": [HumanMessage(content=request.question)]
        },
        config={
            "configurable": {
                "thread_id": f"{identity_scope}:{thread_id}"
            }
        },
        context=MeridianContext(employee_api_key=employee_key),
    )

    return {
        "question": request.question,
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "status": result.get("status", "unknown"),
        "thread_id": thread_id
    }


