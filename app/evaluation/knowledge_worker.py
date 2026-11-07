"""One isolated live knowledge case, with no checkpoint or transcript writes."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from app.evaluation.scoring import score_knowledge


def run(case):
    previous = os.environ.get("MERIDIAN_MCP_ENABLED")
    os.environ["MERIDIAN_MCP_ENABLED"] = "false"
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from app.agent.graph import workflow
            from langchain_core.messages import HumanMessage
            # Compile a fresh graph without the application's persistent checkpointer.
            graph = workflow.compile()
            state = graph.invoke({"question": case["question"], "messages": [HumanMessage(content=case["question"])]})
        checks, observations = score_knowledge(case, state)
        return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "observations": observations}
    except Exception as error:
        quota = getattr(error, "status_code", None) == 429 or getattr(error, "status", None) == 429 or any(word in str(error).lower() for word in ("tokens per day", "rate_limit_exceeded", "tokens per minute"))
        return {"status": "error", "error_type": type(error).__name__, "provider_limited": quota}
    finally:
        if previous is None:
            os.environ.pop("MERIDIAN_MCP_ENABLED", None)
        else:
            os.environ["MERIDIAN_MCP_ENABLED"] = previous


if __name__ == "__main__":
    case = json.load(sys.stdin)
    # Import-time SqliteSaver initialization also stays away from real chats.
    with TemporaryDirectory(prefix="copilot-evaluation-") as directory:
        os.environ["COPILOT_CHECKPOINT_DB"] = str(Path(directory) / "scratch.sqlite")
        result = run(case)
        module = sys.modules.get("app.agent.graph")
        connection = getattr(module, "conn", None)
        if connection is not None:
            connection.close()
    print(json.dumps(result))
