# Repeatable evaluation scorecard

The scorecard covers policy/source linkage, clarification, ticket creation,
ownership, employee closure/admin permissions, and model/MCP/database failures.
It also checks current admin confirmation, browser revocation, and ticket review
protections. `evals/test_cases.json` retains the 98 knowledge questions;
`evals/workflow_cases.json` names 28 focused runtime/backend scenarios.

## Run from CMD

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\activate
python -m app.evaluation.scorecard --profile checks --output evals/reports/checks
```

This runs 15 provider-mocked runtime checks and 13 real PostgreSQL/API permission
checks. Backend tests use `backend/.venv` and `backend/.env`, with generated
records inside rollback-isolated transactions. Existing user passwords are not
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
Creation deduplication is checked within a single tool loop; cross-request HTTP
idempotency is not certified by that case.

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
