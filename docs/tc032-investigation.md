# tc-032: where the answer disappears

Live evaluation remains stopped. No Groq, Pinecone or web-search requests were
made during this investigation. The 44 completed live cases still contain 36
passes and eight failures; this work does not replace those observations.

## Preserved evidence

The complete `evals/reports/expanded-initial/` report set was copied to
`evals/reports/baseline-before-tc032-debug/`. Its `sha256.json` manifest verifies
the archived and original files are unchanged. `tc-032` retains its original
expectation hash and failed result in `batch-005.json` and `coverage.json`.

The question is “How long is a Temporary Access Pass valid?” The expected answer
is eight hours, single use, supported by `KB-IAM-0015`.

## Trace and limits of the historical report

| Stage | What can be established |
| --- | --- |
| Knowledge content | Local `mfa_enrollment_and_recovery.md`, section 5.2, explicitly says “A single-use code valid for 8 hours.” Sections 9 and 10 repeat the fact. |
| Pinecone retrieval | The historical report lists `KB-IAM-0015` among retrieved documents. It does **not** retain chunk IDs or text, so document recall alone cannot prove the specific fact was retrieved. |
| Relevance grader | It returns a boolean for the whole context; it does not filter individual chunks. In this fresh evaluation graph, generation without classification means retrieval was accepted. |
| Generator input | The generator receives every retrieved chunk's full `text` value; no separate context truncation/filter is applied here. The historical payload was not retained, so its precise contents cannot be reconstructed. |
| Generation and safeguard | The saved status is `insufficient_context`, while classification was not run. With this code path, the internal generator ran and returned `grounded=False`, which `generate_response()` maps to that status. The expected document was present, so the no-chunks branch does not explain it. |
| Lost evidence | The original candidate, finish reason and guard rejection code were discarded. Missing/unsupported labels, unknown source IDs, an empty candidate and a non-`stop` completion cannot be distinguished retrospectively. |

The answer disappears **at the generation/safeguard boundary**, not because the
grader routed the request to fallback. This conclusion is inferred from the
stateless graph's code path and saved state. It does not establish that the
historical candidate contained the correct fact.

## Targeted fix: retain the rejection evidence

The demonstrated implementation defect is diagnostic data loss: every guard
failure became the same generic clarification and discarded its explanation.
Validation now returns the same acceptance decision plus specific rejection codes:

- `empty_answer`
- `missing_citation_labels`
- `unknown_source_ids`
- `incomplete_generation`

The generators preserve safe diagnostics through graph state into evaluation
observations: candidate/context lengths and SHA-256 digests, source count and
recognized source numbers, finish reason, requested output budget, and available
prompt/completion/reasoning token counts. The worker also records retrieved chunk
IDs, document IDs, text lengths/digests and the relevance decision. An
evaluation-scoped probe records literal expected-keyword presence before the
guard; this is a lexical observation, not proof of factual accuracy.

No raw candidate, prompt, source text or credentials are added to reports. No
additional model call or retry was added. The citation gate, output budgets,
routing and evaluation expectations remain unchanged.

## Offline regression

`tests/test_tc032_trace.py` recreates the current local chunks and supplies a TAP
chunk that contains the required fact. It executes the real stateless graph,
prompt builders, guard and scorer. Pinecone and Groq responses are mocked, and
socket connections are blocked. Both the grader prompt and generator prompt are
asserted to contain the actual eight-hour policy sentence.

| Controlled candidate | Completion | Guard decision | Final result |
| --- | --- | --- | --- |
| Correct eight-hour fact without a label | `stop` | Reject: missing label | `insufficient_context` |
| Correct eight-hour fact with `[Source 1]` | `length` | Reject: incomplete generation | `insufficient_context` |
| Correct eight-hour fact with a supplied label, in either supported bracket style | `stop` | Accept | `answered`; unchanged `tc-032` checks pass |

The first two tests verify that literal `8` is present before validation and
absent after the candidate is replaced. These are **controlled reproductions of
possible causes**, not reconstructions of the original live output. Results are
saved at `evals/reports/tc032-offline-trace.json` and `.md`.

## Next live diagnostic, after quota availability is confirmed

Only rerun the relevant case, preserving the failed baseline:

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python.exe -B -m app.evaluation.scorecard --profile knowledge --ids tc-032 --limit 1 --baseline evals/reports/baseline-before-tc032-debug/tc032-baseline.json --output evals/reports/tc032-after-diagnostics
```

That comparison uses unchanged case expectations. A new pass would be a live
observation, not proof the diagnostics change improved generation. Inspect the
new `observations.pipeline` first:

1. Match returned chunk digests against local chunks to check whether the exact
   TAP fact was supplied. Do not infer fact coverage from a document ID alone.
2. Check `retrieval_relevant` and generation `source_kind`.
3. Check the candidate's literal `8` probe, finish reason, token counts and guard
   rejection reasons. Presence of `8` alone does not prove a correct answer.
4. Only then choose a generation/retrieval fix. For example, truncation warrants
   investigation of reasoning/output budget; missing citations warrant a
   generation-format fix. Neither warrants accepting invalid output.

The underlying live generation cause and any answer-quality fix remain pending
that evidence. No live rerun or background resume has been started.
