# Expanded evaluation progress: Gemini 3.5 Flash-Lite

## Completed baseline and quality follow-up

Gemini completed the final range `tc-082`–`tc-098`, including a preserved-error,
paced retry of the last two cases. The full catalog now has **98/98 completed
outcomes: 83 passed, 15 failed, zero errors/skips**. Historical checksums and all
previously completed outcomes verified unchanged. The frozen full reports are in
`completed-98-baseline/` under the main run directory.

The [joint answer-quality investigation](answer-quality-investigation.md) reviews
all 15 failures and implements strict, model-declared source-ID rendering without
changing citation acceptance or case expectations. All 158 offline tests passed.
A separately saved four-case same-model check improved `tc-073` from failed to
passed, retained `tc-045` as passed, and kept `tc-054`/`tc-072` as document-coverage
failures. These new passes were not substituted into the frozen 98-case baseline.
No evaluations remain running or scheduled. Earlier progress entries below are
historical observations, not the current completion count.

## November 9 continuation

The next-day resume is retained in `groq-resume-20261109T055501Z/` under the main
run directory. The saved reset window had expired; one readiness request passed
in **1.012767 seconds**. Groq / `openai/gpt-oss-20b` remained the selected provider.
There were no provider switches or changes to timeouts, source expectations or
citation safeguards.

Batch 009 ran `tc-077`–`tc-081`: `tc-078`, `tc-079` and `tc-081` passed;
`tc-077` and `tc-080` failed quality checks. Both failed web responses finished
with `stop`, but had no recognized inline citation labels, so the safeguard
returned `insufficient_context`. This links the two requested quality symptoms
at a recorded boundary; it does not recover the raw answers or establish whether
they omitted attribution or used an unsupported format. Candidate text was not
saved. Full joint analysis remains pending completed coverage.

Batch 010 started `tc-082`–`tc-086`, but Groq returned **HTTP 429 on `tc-082`**;
the remaining four cases were skipped immediately. Coverage is now
**81/98 completed, 17 unfinished**: **67 passed, 14 failed, 1 error, 16 skipped**.
The next unfinished range is `tc-082`–`tc-098`. All previously completed outcomes
and historical batch checksums verified unchanged in the resume's summary.

The saved response date is **November 9, 06:01:03 UTC**. Its request-reset
interval of **28m48s** exceeds `retry-after: 9` and token reset `44.1s`, so the
conservative next-readiness deadline is **06:29:51 UTC / 11:59:51 AM IST on
November 9**. Expiry is not a guarantee of service availability. No automatic
resume or further live calls were started after the 429.

### Batch-boundary pacing correction

This invocation selected a 60-second delay between cases to reduce bursts. Review
showed that the scorecard intentionally omits a delay after its last case, while
the parent runner previously started the next batch without a delay. Thus this
setting did not apply across batch boundaries. The new runner now waits the same
configured interval before each subsequent batch. The saved error alone does
not establish that this gap caused the 429 or identify the exhausted quota.

The correction was made **after** the live run; the run's source snapshot
preserves the earlier code. All **9 offline batch-runner tests passed**, including
an event-order regression proving that the delay occurs between batches and that
no extra sleep/call happens after a rate-limit stop or a maximum-batch boundary.
No additional live calls were made to test the change.

## Latest Groq resume: 2026-11-08 17:49 UTC

The saved cooldown was checked and had expired. One Groq readiness request passed
in **1.278817 seconds** with zero retries. Batch 008 then ran with Groq /
`openai/gpt-oss-20b`: `tc-076` passed; `tc-077` received **HTTP 429**. All remaining
calls stopped immediately and `tc-078`–`tc-080` were marked skipped in this batch.

Evidence, a fresh baseline/source snapshot, checksum manifest and verification
are retained in `groq-resume-20261108T174920Z/` under the main run directory.
All previous completed results and historical batch checksums verified unchanged.
Current coverage is **76/98 completed, 22 unfinished**: **64 passed, 12 failed,
1 error and 21 skipped**. The unfinished range is now `tc-077`–`tc-098`.

The longest valid reset interval in the new response is **604.8 seconds** from
the request-reset header, producing a not-before time of **2026-11-08
18:00:01.8 UTC / 23:30:01.8 IST**. A future readiness request should wait until at
least **23:30:02 IST**. That historical deadline does not guarantee renewed quota.
No automatic resume is scheduled. Timeouts, expectations and prior failures were
unchanged.

## Latest continuation with direct Groq fallback

The user's revised instruction was to continue until a rate limit, switching
directly to Groq after a Gemini error. Evidence is preserved under
`fallback-resume-20261108T172348Z/` inside the main run directory.

- Batch 006 used Gemini / `gemini-3.5-flash-lite`. `tc-073` completed with a
  quality failure. `tc-075` received HTTP 503; the batch immediately checkpointed
  and skipped its remaining cases for fallback.
- Batch 007 used Groq / `openai/gpt-oss-20b`. `tc-075` completed with a quality
  failure. `tc-076` received **HTTP 429**, so all remaining provider calls stopped.
- Current coverage is **75/98 completed, 23 unfinished**: **63 passed, 12 failed,
  1 error and 22 skipped**. The 23 unfinished cases are `tc-076` through `tc-098`.
- All previously completed outcomes, including the original eight failures,
  remain unchanged. Earlier service errors and subsequent attempts remain in
  separate provider/model-labelled batch files. Historical checksums verified.
- Eight offline batch-runner tests passed before this continuation, including
  the new first-error checkpoint/stop mode. `--stop-on-error` enables explicit
  fallback between complete attempt reports; it does not change a provider or
  retry inside a worker. There are no automatic provider calls left running.

The fallback session contains a fresh source snapshot, baseline, SHA-256 manifest,
non-secret per-provider selections, event log and `run-summary.json`. The
requested 98/98 failure-analysis milestone remains pending completion of the
23 unfinished cases. No evaluation expectations or citation safeguards changed.

## Latest resume: 2026-11-08 17:14 UTC

The explicitly requested continuation is preserved under
`evals/reports/gemini35-remaining-20261108T170129Z/resume-20261108T171445Z/`.
Readiness passed in **1.348686 seconds**, with zero retries. A fresh baseline,
source snapshot and SHA-256 manifest identify the source used for this resume.
Existing timeouts and evaluation expectations were unchanged.

| Batch | Cases | Passed | Quality failures | Errors |
| --- | --- | --- | --- | --- |
| 004 | `tc-063`, `tc-066`–`tc-069` | 5 | 0 | 0 |
| 005 | `tc-070`–`tc-074` | 3 | 1 (`tc-072`) | 1 (`tc-073`) |

The earlier `tc-063` error was successfully retried; its original failed attempt
remains in batch 003. `tc-072` retrieved both expected documents but cited only
the VPN document. Its generation finished normally and passed the citation
safeguard, so its failed check is expected-document coverage rather than invalid
source labels or a timeout. No expectations or baseline failures were changed.

`tc-073` returned HTTP 503 from Gemini. The remaining case, `tc-074`, passed;
the runner stopped before batch 006 because of that service error.
The current consolidated report is **73/98 completed, 25 unfinished**:
**63 passed, 10 failed, 1 error, 24 not yet run**. The original eight failures and
the newer `tc-054` failure remain intact; `tc-072` is the tenth quality failure.
Per-case provider/model labels and all earlier attempt reports remain available.

The resume's `preservation-verification.json` confirms historical batch/seed
checksums and all 64 previously completed outcomes/checks were unchanged.
Coverage is still incomplete, so the requested final failure-pattern analysis
and targeted application fixes remain pending. The next unfinished case is
`tc-073`, followed by `tc-075` onward. For a future resume, use this resume's
`baseline.json` plus all existing batch files, or snapshot the latest consolidated
coverage as a fresh seed; do not restart from an outdated unlabelled seed.

## Earlier continuation

The continued run is preserved under
`evals/reports/gemini35-remaining-20261108T170129Z/`.
Three five-case batches ran with `gemini` / `gemini-3.5-flash-lite`, unchanged
evaluation expectations, 30-second provider phase limits, 120-second whole-case
deadlines and ten seconds between cases. Running Docker settings were unchanged.

| Batch | Cases | Passed | Quality failures | Errors |
| --- | --- | --- | --- | --- |
| 001 | `tc-051`–`tc-055` | 4 | 1 (`tc-054`) | 0 |
| 002 | `tc-056`–`tc-060` | 5 | 0 | 0 |
| 003 | `tc-061`–`tc-065` | 4 | 0 | 1 (`tc-063`) |

`tc-063` received **HTTP 503** during internal relevance grading after retrieval
completed. The two remaining cases in that batch passed. The runner stopped
before another batch because of the provider service error; it did not retry it
or change timeouts. There were no rate-limit or transport-timeout errors in these
three batches. A 503 does not establish when the service will be ready again.

## Consolidated coverage and provider labels

Coverage is **64/98 completed, 34 unfinished**: 55 passed, 9 failed, 1 error and
33 never-run/skipped. The incomplete overall gate fails, as expected.

| Provider / model | Passed | Failed | Error |
| --- | --- | --- | --- |
| Historical Groq / `openai/gpt-oss-20b` | 37 | 8 | 0 |
| Gemini / `gemini-3.5-flash-lite` | 18 | 1 | 1 |

These counts reflect latest unfinished retries plus immutable completed
observations across different source revisions. They are completion tracking,
not a controlled provider comparison. Provider/model labels are present per case
in the new `coverage.json` and `coverage.md`.

Forty-four old cases originally recorded a model but no provider field. Their
Groq labels are explicitly attributed using historical run documentation and the
Groq client import at the recorded Git revision. `provider-attribution.json`
records that distinction; original reports were not changed. Some old runs had
dirty source trees, so the exact historical source cannot be reconstructed from
their Git revision alone. New runs retain source snapshots and hashes.

## Preservation and runtime controls

- The eight original failures remain unchanged: `tc-008`, `tc-013`, `tc-014`,
  `tc-027`, `tc-032`, `tc-038`, `tc-040`, `tc-043`.
- `tc-054` is an additional observed failure: both expected documents were
  retrieved, but only the VPN document was actually cited. Generation completed
  normally and the citation safeguard accepted its supplied label. This is a
  document-coverage failure, not a provider timeout or proof of factual error.
- Completed outcomes are locked when reports are consolidated. Subsequent
  overlapping passes cannot erase a failure. Errors/skips can be retried, while
  all their original attempt reports remain available.
- Each completed case atomically checkpoints the batch JSON before the next
  call. Unfinished cases are explicitly marked pending/skipped. An interrupted
  invocation can recover completed cases from those batch files.
- A rate limit stops remaining calls immediately. Two transport failures stop
  calls within a batch; the runner also counts them across batches in the same
  invocation. Other evaluation/service errors stop before a subsequent batch.
  The transport counter resets on an explicitly requested new invocation.
- `preservation-verification.json` confirms all pre-run historical report
  checksums match and all 50 completed baseline outcomes/checks remain unchanged.
  Source archives, catalogs, expectation hashes and the original provider selector
  are retained in the run directory without credentials or raw policy text.

The full offline suite passed **141 tests** before the live run. Afterward, all
**7 batch-runner tests** passed, including the additional historical-provider-label
test. The controls also cover rate-limit stopping, repeated transport errors,
checkpoint callbacks, failure preservation, nested provenance and bounded batches.

## Next work after service availability returns

Resume from the labelled seed in the same directory so the next report is
`batch-004`, rather than overwriting an earlier attempt. With the selected provider
configuration and credentials loaded privately, the runner arguments are:

```text
--exclude-report evals/reports/gemini35-remaining-20261108T170129Z/provider-labelled-seed.json
--output-dir evals/reports/gemini35-remaining-20261108T170129Z
--batch-size 5 --delay 10 --timeout 120
```

The next unfinished case is `tc-063`, followed by `tc-066` onward. Preserve a new
source snapshot before using changed code. Do not reuse the historical Gemini or
Groq model selection accidentally; the run's `selection.env` identifies this model.

The requested full failure-pattern analysis and application fixes are **pending
98/98 completed coverage**, not claimed complete here. Preliminary saved symptoms
are citation omission/guard rejection, route mismatches and the new multi-document
citation-coverage failure. Old reports lack the raw candidate and some diagnostics,
so those symptoms cannot establish every historical root cause. Any later fix
needs an evidence-based regression and a separate before/after report; it must
not weaken citation safeguards or replace these baseline failures.
