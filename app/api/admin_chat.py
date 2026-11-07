"""Authenticated review/confirmation boundary for chat-proposed admin writes."""
import json
from fastapi import APIRouter, Header, HTTPException, Query, Response
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field
from app.services.meridian_auth import backend_request


class ActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thread_id: str = Field(min_length=1, max_length=100)


def create_router(store, agent, history):
    router = APIRouter(prefix="/admin/chat/actions", tags=["Admin chat confirmation"])

    def identity(authorization, response):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in required")
        user = backend_request("/auth/me", authorization=authorization)
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required")
        response.headers["Cache-Control"] = "no-store"
        return f"user:{user['id']}"

    @router.get("")
    def pending(response: Response, thread_id: str = Query(min_length=1, max_length=100), authorization: str | None = Header(default=None)):
        scope = identity(authorization, response)
        return {"items": store.list(scope, thread_id)}

    @router.post("/{action_id}/cancel")
    def cancel(action_id: str, data: ActionDecision, response: Response, authorization: str | None = Header(default=None)):
        scope = identity(authorization, response)
        return store.cancel(scope, data.thread_id, action_id)

    @router.post("/{action_id}/confirm")
    def confirm(action_id: str, data: ActionDecision, response: Response, authorization: str | None = Header(default=None)):
        scope = identity(authorization, response)
        if history.is_archived(scope, data.thread_id):
            raise HTTPException(status_code=409, detail="Restore the conversation before confirming changes")
        result = store.confirm(scope, data.thread_id, action_id, authorization)
        # Public outcome only; setup credentials are deliberately excluded.
        message = "Confirmed admin action completed: " + json.dumps(result["result"], ensure_ascii=False)
        try:
            agent.update_state({"configurable": {"thread_id": f"{scope}:{data.thread_id}"}}, {"messages": [AIMessage(id="admin-action-" + action_id, content=message, additional_kwargs={"status": "admin_action_completed", "sources": []})]}, as_node="save_response")
        except Exception:
            result["history_warning"] = "The action completed, but its chat history could not be updated. Do not repeat it."
        return result

    return router
