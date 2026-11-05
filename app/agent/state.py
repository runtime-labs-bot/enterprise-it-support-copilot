from typing import TypedDict


class AgentState(TypedDict, total=False):
    question: str
    retrieved_chunks: list[dict]
    grading_result: dict
    answer: str
    sources: list[dict]
    status: str
    classification: dict
    web_results: list[dict]
    web_grading_result: dict


    