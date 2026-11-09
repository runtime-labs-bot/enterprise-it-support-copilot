# Stage timeout diagnostics

Knowledge scorecard results now include `stage_diagnostics` on successful and
failed worker runs. Instrumentation is opt-in and leaves routing, citation
requirements, request budgets and timeout settings unchanged.

| Stage | Boundary |
| --- | --- |
| `retrieval` | Pinecone initialization, queries and document retrieval; web retrieval is separately identified by component/provider |
| `relevance_grading` | The internal or web relevance LLM call |
| `answer_generation` | The internal or web grounded-answer LLM call |
| `citation_safeguard` | Local citation and completion validation |

Classification is recorded as an additional stage when that route runs. Each
event records its component, provider, model, elapsed seconds, status, timeout
category, effective timeout and retry count when available. LLM calls also record
request count and configured connect/read/write/pool limits. The adapter performs
zero automatic retries; Pinecone retry counts are unknown and therefore `null`.
Pinecone has no LLM model, so that field is also `null`.

Timeout categories distinguish `connect`, `read`, `write`, `pool` and unspecified
timeouts. A normal citation rejection has status `rejected`, with safe reason
labels, rather than a timeout. The safeguard records the generating provider/model
for attribution; validation executes locally and makes no provider request.
Stages not reached are explicitly `not_run`, with no invented elapsed time.

Completed events survive a later stage exception. A worker forcibly terminated
by the outer process deadline cannot return its in-memory trace. These events do
not store prompts, policy text, employee information, response bodies, API keys
or exception messages.

## Offline verification

The full root unit suite passed **137 tests** before the readiness request.
New tests cover success, retrieval/grading/generation timeouts, citation rejection,
elapsed timing, context isolation, privacy and exactly-one-request readiness
behavior. Provider HTTP uses mocked transport and socket connections are blocked.

```bat
.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_stage_diagnostics.py
```

## Observed readiness result

After offline checks passed, exactly one minimal JSON completion was attempted.
Its report is saved locally in `evals/reports/llm-readiness-001.json`:

| Field | Observed value |
| --- | --- |
| Provider / model | `gemini` / `gemini-3.8-flash` |
| Stage / component | `relevance_grading` / `readiness_json` |
| Elapsed | 97.729072 seconds |
| Timeout category | `read` (`ReadTimeout`) |
| Effective per-phase limit | 90 seconds |
| Requests / retries | 1 / 0 |
| Ready | false |

This request used the same transient 90-second limit as the preceding evaluation
retries. Persistent settings were not changed. The minimal probe contains no
retrieval or employee context. Its failure prevented the conditional `tc-045`
retry; the last historical case report remains `batch-013.json`.

The probe establishes that minimal JSON generation timed out. It does not locate
the failed stage in the historical `tc-045` attempt, nor distinguish provider
capacity from network delivery problems. No further live requests were made.

An explicitly requested future probe can use:

```bat
.venv\Scripts\python.exe -B scripts\check_llm_readiness.py --live --env-file .env.docker
```

The script saves a new report without overwriting prior evidence. It makes one
request and never resumes evaluation automatically. It uses the selected current
configuration; it does not reproduce a historical transient timeout override.
