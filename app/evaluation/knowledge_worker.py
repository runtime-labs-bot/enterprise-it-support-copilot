"""One isolated live knowledge case, with no checkpoint or transcript writes."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from app.evaluation.scoring import score_knowledge
from app.services.generation_diagnostics import probe_generation
from app.services.stage_diagnostics import capture_stages, finalize_stages


def run(case):
    stages = []
    previous = os.environ.get("MERIDIAN_MCP_ENABLED")
    os.environ["MERIDIAN_MCP_ENABLED"] = "false"
    try:
        with capture_stages(stages), probe_generation(case.get('expected_keywords', [])), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from app.agent.graph import workflow
            from langchain_core.messages import HumanMessage
            # Compile a fresh graph without the application's persistent checkpointer.
            graph = workflow.compile()
            state = graph.invoke({"question": case["question"], "messages": [HumanMessage(content=case["question"])]})
        checks, observations = score_knowledge(case, state)
        observations['pipeline'] = {
            'retrieved_chunks': [{'chunk_id': chunk.get('id'), 'document_id': chunk.get('document_id'),
                                  'characters': len(chunk.get('text', '')),
                                  'text_sha256': sha256(chunk.get('text', '').encode()).hexdigest()}
                                 for chunk in state.get('retrieved_chunks', [])],
            'retrieval_relevant': (state.get('grading_result') or {}).get('relevant'),
            'generation': state.get('generation_diagnostics', {}),
        }
        return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "observations": observations, 'stage_diagnostics':finalize_stages(stages)}
    except Exception as error:
        quota = getattr(error, "status_code", None) == 429 or getattr(error, "status", None) == 429 or any(word in str(error).lower() for word in ("tokens per day", "rate_limit_exceeded", "tokens per minute"))
        result = {"status": "error", "error_type": type(error).__name__, "provider_limited": quota, 'stage_diagnostics':finalize_stages(stages)}
        http_status = getattr(error, 'status_code', None)
        if type(http_status) is int and 100 <= http_status <= 599:
            result['http_status'] = http_status
        if getattr(error, 'error_kind', None) in {'transport','invalid_response','http_status'}:
            result['provider_error_kind'] = error.error_kind
        if getattr(error, 'transport_error', None) in {'ConnectError','ReadError','WriteError','ConnectTimeout','ReadTimeout','WriteTimeout','PoolTimeout','RemoteProtocolError','LocalProtocolError'}:
            result['transport_error'] = error.transport_error
        if quota and getattr(error, 'reset_headers', None):
            result['rate_limit_headers'] = error.reset_headers
            from datetime import datetime, timezone
            from app.evaluation.rate_limits import retry_window
            result['retry_window'] = retry_window(error.reset_headers, datetime.now(timezone.utc).isoformat())
        return result
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
