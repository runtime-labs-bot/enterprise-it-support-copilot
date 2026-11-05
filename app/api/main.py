from fastapi import FastAPI
from pydantic import BaseModel

from app.agent.graph import app as agent

#creating a fastapi application

app = FastAPI(
    title="IT Support Copilot API",
    description="Backend API for our Agentic RAG IT Support Copilot",
    version="1.0.0"
)

# Define the incoming request structure
class QuestionRequest(BaseModel):
    question :str

#first api endpoint

@app.get("/")
def home():
    return {
        "message":"Welcome to IT Support Copilot API"
    }

#POST ENDPOINT to ask questions
@app.post("/ask")
def ask_question(request:QuestionRequest):

    result = agent.invoke(
        {
            "question":request.question
        }
    )

    return {
        "question": request.question,
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "status": result.get("status", "unknown")
    }



