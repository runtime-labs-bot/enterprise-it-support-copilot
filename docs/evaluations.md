# Repeatable evaluation scorecard

Current catalog note: `tc-054` and `tc-072` have documented expectation revision 2
after source-sufficiency review. Their old v1 report hashes intentionally do not
compare as compatible. Preserve the frozen 98-case baseline; use separately
labelled v2 checks rather than merging new expectations into old scores. See the
[credential/policy review](credential-policy-followup.md) for rationale and tests.

The scorecard covers policy/source linkage, clarification, ticket creation,
ownership, employee closure/admin permissions, and model/MCP/database failures.
It also checks current admin confirmation, browser revocation, and ticket review
protections. `evals/test_cases.json` retains the 98 knowledge questions;
`evals/workflow_cases.json` names 42 focused runtime/backend scenarios.

## Run from CMD

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\activate
python -m app.evaluation.scorecard --profile checks --output evals/reports/checks
```

This runs 20 provider-mocked runtime checks and 22 real PostgreSQL/API permission
checks. Backend tests use `backend/.venv` and `backend/.env`, with generated
records inside rollback-isolated transactions. The independent-session race test
commits its own generated employee/ticket fixture so both clients can see it,
then removes those fixture records in a `finally` block. Existing user passwords are not
changed. PostgreSQL identity sequences can advance even though records roll back.
`--profile offline` runs only the runtime checks and needs no live providers or
database; outbound provider connections are blocked in its worker. Loopback is
allowed for Windows asyncio internals.

For one combined report including live knowledge quality:

```bat
python -m app.evaluation.scorecard --profile all --limit 5 --output evals/reports/latest
```

The default five live cases are `tc-001`, `tc-005`, `tc-015`, `tc-017`, `tc-022`:
password reset, VPN policy, unknown company policy, an off-topic request, and a
numeric password-policy fact. The offline/backend checks always run in full;
`--limit` limits **only knowledge calls**. Live runs consume provider tokens and
use the existing Groq/Pinecone/Tavily configuration.

Target specific questions, tags, or the complete knowledge catalog:

```bat
python -m app.evaluation.scorecard --profile knowledge --ids tc-001,tc-015,tc-022 --limit 3
python -m app.evaluation.scorecard --profile knowledge --tag vpn --limit 10
python -m app.evaluation.scorecard --profile knowledge --limit 98 --delay 10
```

Each live case runs in its own subprocess with a fresh graph, no persisted
conversation/checkpointer, and an isolated temporary initialization database.
`--timeout` defaults to 120 seconds per live case/workflow batch. A provider quota
error stops remaining live calls and explicitly marks them skipped. A timeout is
an error. Neither is counted as a pass.

The old command `python -m app.evaluation.run_evaluation --limit 5` now delegates
to the live knowledge scorecard and avoids the old missing-thread-ID problem.
The retrieval-only evaluator remains available separately for search diagnostics.

## Reading the results

Every run writes `.json` and `.md` files at the chosen output prefix. Generated
reports under `evals/reports/` are ignored by Git. They contain:

- Per-case passed/failed/error/skipped outcomes and failed check names.
- Per-area totals and pass rates; unselected areas display **Not run**.
- Critical-failure gating, selected profile/configuration, expectation hashes,
  Git revision/dirty state, Python version and configured model name.
- Retrieval recall and **cited** document recall as separate observations.
- No raw model answers, retrieved text, credentials, passwords, or token bodies.

Knowledge checks require the expected result status, relevant expected documents,
valid inline `[Source N]` or `【Source N】` references tied to supplied chunk IDs or supplied web
URLs, and actual citation of the expected policy documents. Retrieving the right
document without citing it does not pass. Numeric keyword checks use word
boundaries and common spelled-out variants. Unknown-policy responses must ask
for more context without inventing source cards. Classification is scored only
when the graph actually performs classification; this is reported explicitly.

These are verifiable source-linkage and lexical checks, **not proof that every
sentence is entailed by a source**. Human review or a separately calibrated judge
is still needed for semantic quality. Scripted runtime tests prove tool-loop
behavior under specified model outputs; they do not prove that a live model will
always choose the right tool. PostgreSQL checks prove backend enforcement.
Creation deduplication within one tool loop and durable cross-request ticket
idempotency have separate cases. PostgreSQL race tests verify one ticket and one
creation event for concurrent requests with the same authenticated actor/key.

The default gate requires 100% of selected cases to pass. `--fail-under 0.95`
can relax ordinary quality failures, but critical failures, errors, and skipped
cases always fail. Empty selections are rejected. Exit 0 means the scoped gate
passed; exit 1 means an observed evaluation failure, not necessarily a runner bug.

## Baselines and combining runs

```bat
python -m app.evaluation.scorecard --profile checks --output evals/reports/baseline
python -m app.evaluation.scorecard --profile checks --baseline evals/reports/baseline.json --output evals/reports/current
```

Baseline comparisons require exactly the same selected IDs and expectation
hashes. A previously passing case becoming non-passing fails the comparison.
Changed expectations or incompatible selections require a reviewed new baseline.
Code changes are allowed: baseline comparison is intended to catch their effects.

Separate checks/live reports can be combined without spending more provider tokens:

```bat
python -m app.evaluation.scorecard --merge evals/reports/checks.json evals/reports/knowledge-sample.json --output evals/reports/latest
```

Merge preserves failures, rejects duplicate IDs or outdated expectations, and
retains source-run provenance. It does not claim a new evaluation was executed.

## Initial observed result

The current run passed all **28 runtime/backend scenarios**. A three-case live
sample passed `tc-001` (password reset with citations) and `tc-015` (unknown-policy
clarification). `tc-022` returned the expected minimum-length fact but failed the
inline citation checks. The combined score was **30/31**, with the strict quality
gate correctly failing. This is a genuine follow-up quality issue to investigate;
the evaluator was not relaxed to hide it. This sample is not a claim about all
98 knowledge questions, and live model results can vary between runs.

### `tc-022` diagnosis

A separate diagnostic run on November 7, 2026 reproduced the failure. The model
answered: “The minimum password length for all corporate accounts is **14
characters**【Source 1】.” Source 1 mapped to the retrieved password policy,
`password_reset_and_unlock-chunk-002` (section 2, Password Policy Summary).
Generation finished normally (`finish_reason=stop`, 92 completion tokens against
an 800-token budget).

The evaluator's `citation_numbers()` recognizes ASCII `[Source 1]` but not Unicode
`【Source 1】`. An offline isolation check changed only those brackets; all three
citation checks then passed with the same source/chunk linkage. This reproduction
therefore identifies a citation-format compatibility issue, rather than missing
retrieval or missing attribution. The original run did not retain its raw answer,
so its exact citation spelling cannot be recovered retrospectively.

Recommended follow-up: recognize this bracket variant with regression coverage,
while keeping source-ID and retrieved-chunk validation mandatory. Preserve the
original failed reports; a future corrected evaluation should be a separate run.
No scoring or answer-generation behavior was changed during that diagnosis.

### Citation parser regression run

The follow-up parser accepts both bracket styles with matching pairs. Regression
tests cover both styles, combined labels, mismatched brackets, fabricated source
IDs, and fabricated chunk IDs. Source linkage and expected-document checks remain
mandatory; the model prompt and case expectations were not changed.

The original three-case live report and combined failed report were copied into
`evals/reports/baseline-before-citation-parser/`, with SHA-256 checksums. The
original report paths are also retained. The five smoke cases run separately at
`evals/reports/citation-parser-five.json` and `.md`.

Only `tc-001`, `tc-015`, and `tc-022` have historical live outcomes. Compare those
three with the preserved baseline; `tc-005` and `tc-017` are additional evidence,
not historical improvements. A live rerun can vary, so this comparison is not a
controlled replay of the original answers. The unit regression isolates the
parser change independently of model variation.

The follow-up run passed **5/5 live cases**, with no errors or skips. The three
matched historical cases improved from **2/3 to 3/3**, with no regressions and
unchanged expectation hashes. `tc-022` passed every citation check. All **97 local
regression tests** also passed. Archived and original report checksums were
verified unchanged. The detailed comparison is saved separately at
`evals/reports/citation-parser-baseline-comparison.md` and `.json`.

## Expanded live evaluation and CI

Resume the unfinished catalog without rerunning already completed pass/fail cases:

```bat
python scripts\run_knowledge_batches.py --exclude-report evals/reports/citation-parser-five.json --output-dir evals/reports/expanded-initial --batch-size 10 --delay 10
```

Every batch gets a new filename. Provider limits stop further calls. Resume with
the same command after the provider allows requests again; errors and skips are
retried, while existing failed answers remain failed for review. Changed case
expectations are rejected. `coverage.json`/`.md` includes all 98 cases in its
denominator, selects the latest attempt per case, and retains each source report
and its provenance. This is a coverage view, not a new single-version live run.

The first two batches reached provider limits. At that point, including the earlier smoke run, **17/98
cases have completed answers: 14 passed and 3 failed**. The latest outcomes also
include one rate-limit error and 80 skips (77 never requested). **81 cases remain
unfinished**, so the full-catalog gate failed. Original batch reports are retained.

A subsequent resume completed another 27 cases before a rate limit at `tc-045`.
The preserved latest live snapshot is **44/98 completed: 36 passed, eight failed**,
with one rate-limit error, 53 skips and **54 unfinished**. The `tc-032` debugging
baseline preserves this snapshot; no live rerun has been performed during debugging.

| Case | Observed failure | Follow-up |
| --- | --- | --- |
| `tc-008` | Internal answer had no recognized inline labels despite retrieving the expected software policy | Citation guard added; live recheck pending provider availability |
| `tc-013` | Web route/category were correct, but no recognized inline citation labels | Same guard applied to web generation; live recheck pending |
| `tc-014` | Answered from internal VPN context instead of the expected web route | Requires review of document relevance and route expectation; no expectation relaxed |

The original answers were not retained, so the exact label spelling or generation
finish reason in those failures cannot be recovered. The new runtime safeguard
rejects empty, truncated, missing-label, and out-of-range-label responses, returns
a clarification request without source cards, and marks the result
`insufficient_context`. It adds no model retry and does not manufacture citations.
Offline tests verify the safeguard; the preserved live failures have not been
rescored as passes. Source linkage still does not prove semantic entailment.

`.github/workflows/evaluations.yml` runs offline scorecard/regression tests on
pushes and pull requests without provider secrets. Live evaluation is available
only through **Actions > Copilot evaluations > Run workflow**, with `live=true`
and a limit of 1–98. Configure repository secrets `GROQ_API_KEY`,
`PINECONE_API_KEY`, `TAVILY_API_KEY`, and repository variable
`PINECONE_INDEX_NAME`; `GROQ_MODEL` is an optional variable. Reports are uploaded
as workflow artifacts even when the score gate fails. The workflow must be
committed/pushed before GitHub can execute it; local checks do not certify a
hosted Actions run.

Implementation verification passed **106 Copilot unit tests**, **96 backend
tests**, and the expanded **42/42 runtime/backend scorecard**. The new runtime
guard was verified with mocked model responses; provider limits prevented its
live recheck. The implementation was pushed as `f8bc48d`, and the
[hosted offline workflow passed](https://github.com/rushberry02/enterprise-it-support-copilot/actions/runs/42392175730).
The live job was skipped. Docker was rebuilt and all four services are healthy;
the deployed database is at migration `0009_ticket_idempotency`.

See the [offline failure review](evaluation-failure-review.md) for the evidence
behind all three failures and the quota/reset limitation. Live evaluation is
currently stopped; no automatic resume is scheduled. Resume explicitly in batches
of 5–10 after confirming provider availability.

Run the deployed verification without any model calls:

```bat
python scripts\verify_docker_safeguards.py
```

This checks actual concurrent HTTP requests against Docker, repeated-request
identity, changed-payload conflicts, one creation event, and employee isolation.
Generated accounts, tickets and request reservations are removed afterward. It
then runs 10 internal/web citation checks inside the rebuilt Copilot container
with mocked model responses and provider networking blocked. All checks passed;
sanitized evidence is saved locally at `evals/reports/docker-safeguards.json`.

The subsequent [tc-032 investigation](tc032-investigation.md) preserves the
44-completed-case baseline and adds safe per-stage diagnostics plus an offline
regression. It identifies the guard boundary but does not claim to recover the
discarded historical candidate or prove an answer-quality fix. Live evaluation
remains stopped; a one-case baseline-comparison command is provided in that guide.

For the later Gemini retries, see the [offline timeout diagnosis](gemini-timeout-diagnosis.md).
It distinguishes the provider read timer from the whole-case deadline, documents
what the saved attempts cannot prove, and reproduces the error mapping with
mocked transport and socket connections blocked. No live request was made for
that investigation.

The subsequent [stage timeout diagnostics](stage-diagnostics.md) instrument
retrieval, relevance grading, answer generation and citation validation. All 137
root offline tests passed. One minimal Gemini readiness request then hit a read
timeout after 97.73 seconds with zero retries, so `tc-045` was not retried.
Historical reports and persistent timeout settings remain unchanged.

The [alternative-provider benchmark resume](provider-benchmark-resume.md)
subsequently verified Groq readiness and a complete passing live case (`tc-046`).
The five-case resumed batch stopped on a 429 with 1 pass, 2 errors and 2 skips.
Historical reports, expectation hashes and source snapshots were preserved;
combined coverage is mixed-provider completion tracking, not a provider comparison.

The [continued five-case run](expanded-evaluation-progress.md) reached **64/98
completed** using Gemini 3.5 Flash-Lite before an HTTP 503 stopped further batches.
It preserves all eight original failures and adds one document-citation-coverage
failure. Per-case checkpoints and explicit provider/model labels are retained;
34 cases remain unfinished before the requested full failure analysis.

A subsequent explicit resume passed readiness and ran batches 004–005. Current
coverage is **73/98 completed**, with **25 unfinished** after another Gemini HTTP
503. There are 63 passes and 10 preserved quality failures; the latest added
failure is `tc-072` (expected-document citation coverage). Historical checksums
and all previously completed outcomes verified unchanged.

After the user's explicit direct-fallback instruction, batch 006 stopped on a
Gemini HTTP 503 and batch 007 retried unfinished cases on Groq. Groq then returned
HTTP 429 on `tc-076`, stopping all calls. Current coverage is **75/98 completed**,
with 63 passes, 12 preserved failures and 23 unfinished cases. Full evidence and
the new first-error checkpoint mode are described in the continued-run guide.

Future invocations also [respect the longest saved provider reset window](rate-limit-cooldowns.md),
accounting for elapsed time and keeping provider cooldowns separate. An active
window prevents readiness and evaluation calls; it does not trigger an automatic
retry. This change passed 152 offline tests and made no live requests.

The subsequent explicit Groq resume passed readiness and `tc-076`, then stopped
on HTTP 429 at `tc-077`. Coverage is now **76/98 completed**, with **22 unfinished**.
The new conservative reset deadline is November 8, 2026, **23:30:02 IST** (rounded
up); previous results and report checksums verified unchanged.

On November 9, Groq readiness passed and batch 009 completed with 3 passes and
2 quality failures. Batch 010 stopped at `tc-082` on HTTP 429. Current coverage is
**81/98 completed; 17 unfinished**. The longest saved reset points to November 9,
**11:59:51 AM IST**. Missing recognized web citations led to `insufficient_context`
in both new failures; originals are preserved for the requested joint analysis.
A subsequently discovered batch-boundary delay gap was fixed offline, with all
9 batch-runner tests passing; it is not claimed as the proven cause of the 429.

The subsequent Gemini continuation completed **98/98 cases: 83 passed, 15 failed,
zero errors/skips**. The [joint citation/insufficient-context investigation](answer-quality-investigation.md)
freezes that baseline, separates citation formatting from expected-document
coverage, and implements validated per-claim source IDs. All 158 offline tests
passed. A separate same-model four-case check improved from 1/4 to 2/4 without
regressions: `tc-073` now passes, while `tc-054`/`tc-072` remain coverage failures.
The historical full score and original expectations were not changed.
