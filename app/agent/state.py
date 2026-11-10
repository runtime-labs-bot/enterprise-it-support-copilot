from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class AgentState(TypedDict, total=False):
    question: str
    credential_request_blocked: bool
    messages: Annotated[list[AnyMessage], add_messages]

    retrieved_chunks: list[dict]
    grading_result: dict
    generation_diagnostics: dict
    answer: str
    sources: list[dict]
    status: str
    classification: dict
    web_results: list[dict]
    web_grading_result: dict
    contextual_question: str
    meridian_handled: bool
    meridian_tools: list[str]
    admin_proposal: dict | None
