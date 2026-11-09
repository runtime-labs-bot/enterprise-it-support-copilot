# Gemini timeout: offline diagnosis

This investigation made **zero live API requests**. It inspected local code,
non-secret timeout settings and saved attempts, then used a mocked HTTP transport
with socket connections blocked. Existing evaluation reports remain unchanged.

## What failed

`evals/reports/expanded-initial/batch-013.json` records:

- Case: `tc-045`, selected model `gemini-3.8-flash`.
- `provider_error_kind=transport`, `transport_error=ReadTimeout`.
- Total case duration: 101.203 seconds.
- Whole-case subprocess deadline: 300 seconds.
- No HTTP status or token usage returned for the failed request.

The failure occurred inside the provider HTTP client while waiting for network
data, before a complete response reached response normalization. It was not the
outer 300-second watchdog firing. That would have been reported as
`TimeoutExpired`, not `LLMProviderError` / `ReadTimeout`.

## The two timer layers

| Timer | Reported or reconstructed value | Scope |
| --- | --- | --- |
| Scorecard `--timeout` | 300 seconds | Entire worker process, including imports, retrieval, all model calls and scoring |
| Provider `LLM_TIMEOUT_SECONDS` | 90 seconds requested by the retry wrapper and reproduced locally | Each HTTPX network phase: connect, read, write and connection-pool wait |

The retry wrapper explicitly set the provider timeout to 90 when
`.env.docker` did not specify one. Reconstructing that configuration locally
produces `httpx.Timeout(90)` with all four phases set to 90. Neither private env
file currently supplies its own timeout selector. The normal adapter default is
30 seconds; Docker Compose also defaults to 30. The 90-second value belongs to
the evaluation retry process, not a persistent change to the running app.
`batch-013` itself does not retain the effective inner timeout or per-request
elapsed time; distinguish this configuration reconstruction from recorded timing
evidence. The recorded error class does establish that the inner read failed.

An HTTPX read timeout limits the wait for the next network data, including a
possible wait for response headers or a stalled response body. It is not a
guarantee that an entire completion will finish within 90 seconds. Increasing
the subprocess deadline does not increase the inner HTTP read timeout.

The remaining time in the 101.203-second case duration can include Python imports,
Pinecone queries, connection setup, other completed stages and report overhead.
The saved report has no per-stage timings, so it cannot attribute those seconds
precisely. It also cannot identify whether the latest failed call was the
relevance grader, classifier, web grader or answer generator.

## What earlier attempts establish

| Attempt | Saved result | What it establishes |
| --- | --- | --- |
| `batch-010` | One observed HTTP 200 before the overall provider error | At least one request succeeded; it does not establish that a later error was a parsing failure |
| `batch-011` | HTTP 503 during JSON grading | That attempt received an explicit service-unavailable response |
| `batch-012` | ReadTimeout; whole case 116.593 seconds | Another provider transport read failed |
| `batch-013` | ReadTimeout; whole case 101.203 seconds | Same error category on the latest retry, not an evaluation-deadline expiry |

`provider_limited=false` means this attempt did not expose a recognized rate-limit
response. It does **not** prove that quota, account permissions or model capacity
are healthy. Similarly, the earlier successful model-list request does not
guarantee that generation is available or timely.

## What cannot be concluded offline

Provider slowness/capacity problems, delayed network intermediaries, and stalled
response delivery remain possible. The earlier 503 is evidence of an unavailable
service on that attempt, not proof of the latest timeout's exact cause. There is
no basis here to blame citation validation, change the model ID, declare the key
invalid, or relax evaluation expectations.

The HTTP client has `trust_env=False` and no automatic retry or provider fallback.
Pinecone uses a separate client; the observed `LLMProviderError` / `ReadTimeout`
comes from the LLM adapter. Merely increasing all timeouts would postpone the
failure without resolving a confirmed underlying cause.

## Offline regression and next evidence

`test_read_timeout_is_distinct_from_the_outer_case_deadline_without_network`
checks the actual request's HTTPX timeout extensions (90 for each phase), injects
a `ReadTimeout`, verifies the sanitized error through the evaluation worker, and
confirms that an outer 300-second deadline preserves it as a provider error.
Nothing sleeps for 90 seconds or contacts a provider in this regression.

The existing resumable runner uses the scorecard's default 120-second deadline
unless changed in its invocation. That is a separate configuration mismatch to
consider before a future slow-provider batch; it did not cause `batch-013`, whose
deadline was explicitly 300 seconds. No timeout values were changed here.

Before another live retry, the most useful instrumentation would retain the exact
model stage, effective per-phase timeout, and elapsed time for each completed or
failed provider call, without retaining prompts, responses or credentials. A
single explicitly authorized health check could then separate minimal-generation
availability from the full RAG pipeline. Neither check nor evaluation resume was
started during this investigation.
