# Completed 98-case baseline and citation investigation

The [credential and policy follow-up](credential-policy-followup.md) records the
subsequent GitHub/CI/Docker verification, a pre-tool credential-response boundary
and explicit v2 expectation reviews for `tc-054`/`tc-072`. The report below is the
preserved v1 investigation; its historical 83/98 score has not been relabelled.

All **98 knowledge cases have completed outcomes: 83 passed, 15 failed**, with
zero errors or skips. The strict quality gate therefore fails. These are
historical completion results across Groq/Gemini and multiple source revisions,
not a controlled provider comparison or a claim of production readiness.

The final Gemini continuation passed cases `tc-082`–`tc-096`. Its first attempts
at `tc-097` and `tc-098` encountered Gemini 503 and Pinecone connection errors.
A paced retry completed both: `tc-097` passed and `tc-098` failed its expected
response contract. All intermediate reports remain available.

The frozen baseline is under
`evals/reports/gemini35-remaining-20261108T170129Z/completed-98-baseline/`.
`checksums.json` protects the original full JSON/Markdown reports. Their checksums
were verified again after the fix and live validation. `failure-patterns.json`
contains the content-free case grouping below. The original eight failures,
subsequent quality failures, and all provider-error attempts remain unchanged.

## Findings across the pipeline

| Pattern | Cases | What the saved evidence establishes |
| --- | --- | --- |
| Complete web answer rejected for missing recognized citations | `073`, `075`, `077`, `080` | Nonempty generation finished with `stop`; the safeguard recorded `missing_citation_labels` and replaced the candidate with `insufficient_context`. These were not recorded as timeout or truncation failures. |
| Earlier citation failures | `008`, `013` | Answer route completed but citation checks failed. Original candidates/format diagnostics are absent. |
| Earlier insufficient-context responses despite document retrieval | `027`, `032`, `038`, `040` | Expected document IDs were retrieved. Original chunk contents, candidates and guard reasons were not retained, so exact historical causes cannot be reconstructed. |
| Expected-document citation coverage | `054`, `072` | Both expected documents were retrieved; complete answers cited only the VPN document. Valid attribution is distinct from coverage of every expected document. |
| Route expectation mismatch | `014`, `043` | Actual internal/web route differs from the expected route. These need routing/context and expectation review, rather than citation-parser relaxation. |
| Credential-request response contract | `098` | Returned `answered` with a policy citation, rather than source-free clarification. The saved status is not evidence that a credential was disclosed; no raw answer was retained. |

The clearest shared boundary is **generation formatting → citation safeguard →
`insufficient_context`**. For four observed web failures, retrieving more internal
documents, switching providers or raising timeouts does not address the recorded
reason for rejection. The raw answer was not stored, so omission and an unsupported
citation style remain indistinguishable historically.

For the two coverage cases, saved chunk hashes matched **15/15** and **13/13**
current local chunks. Boolean term evidence shows portal/approval material in both
VPN and software documents. This demonstrates available overlapping material;
it does not prove every original answer required two citations or omitted an
important fact. `local-policy-evidence.json` stores only IDs and boolean evidence.
The existing two-document expectation remains unchanged pending semantic review.

## Targeted fix

Both internal and web generation now request a JSON claims object. Each claim
supplies its own explicit integer `source_ids`. The application validates the
whole object and renders those IDs as the existing `[Source N]` labels. It never
assigns a source to an uncited claim or adds other retrieved documents to improve
the score. Existing valid inline answers remain compatible with the same guard.

Invalid JSON/shapes, missing/empty attribution, boolean or string IDs, unknown
IDs, and partially attributed objects fail closed. Embedded unknown citations
also fail the existing guard. Truncated completion still fails even if the JSON
parses. No retries or model/provider switches were added. Output token budgets,
timeouts, retrieval, routing and evaluation expectations remain unchanged.

Safe diagnostics distinguish structured-output errors from missing inline labels
and retain raw/rendered lengths and hashes without the answer text. Internal
generation no longer prints raw question/context prompts to stdout. This does
not certify every other application logging path.

The code is in `app/services/cited_output.py` and the two generators, with local
validation inside the existing citation-safeguard stage. Source linkage validation
does not prove semantic entailment; the model can still attribute a claim to an
incorrect but valid source ID. This fix addresses representation reliability,
not that separate semantic limitation.

## Verification and unchanged baseline

All **158 root offline tests passed**. New regressions cover explicit per-claim
rendering, invalid attribution, rejection of the whole partly invalid answer,
legacy citation styles, no retry, privacy, unknown embedded IDs, unchanged token
budgets, and continued failure when only one of two expected documents is cited.
The new test file is included in the offline CI workflow, which has not been
pushed as part of this work.

A separate live check used the same Gemini provider/model and unchanged case
expectations. Reports are under
`citation-contract-validation-20261109T175847Z/` in the main run directory:

| Case | Before | After | Observation |
| --- | --- | --- | --- |
| `tc-045` | Passed | Passed | Previously passing internal case remains passing. |
| `tc-054` | Failed | Failed | Structured citations validated; expected software-document citation still absent. |
| `tc-072` | Failed | Failed | Same remaining document-coverage mismatch. |
| `tc-073` | Failed | Passed | Web answer now supplies validated source IDs and passes all citation checks. |

Scoped results improved from **1/4 to 2/4**, with **no regressions** and compatible
expectation hashes. The scoped quality gate still fails because two cases fail;
the baseline-comparison gate passes. `comparison.json` records provider/model and
context-hash comparisons. Live outputs and web context vary, so the rerun does
not isolate every difference to the code change; offline tests isolate rendering
and rejection behavior.

The full historical score remains **83/98 passed, 15 failures**. No new passes
were substituted into it. The remaining work is semantic review of the two
coverage cases, routing mismatches and credential-request response contract,
followed by separately preserved, unchanged-expectation checks for older failures.
That initial investigation ended with a local fix; subsequent push, CI,
deployment and contract-review evidence is recorded in the follow-up above.
No evaluations remain running or scheduled.
