# Alternative-provider verification and benchmark resume

## Gemini 3.5 Flash-Lite

The explicitly selected `gemini-3.5-flash-lite` passed one minimal readiness
request on 2026-11-08 in **2.104475 seconds**, with zero retries and the unchanged
30-second per-phase limit. Evidence is retained separately in
`evals/reports/gemini35-lite-resume-20261108T165421Z/`.
This run uses the same local credential that passed Gemini model listing.
It does not update the running Docker app's provider selection.

The bounded benchmark selects the next five unfinished cases: `tc-045`, `tc-047`,
`tc-048`, `tc-049`, `tc-050`. Its source snapshot, expectation hashes, provider/model
selection and copied historical report checksums are retained in the run directory.
Read `batch-001.json` for observed case outcomes and `coverage.json` for updated
mixed-provider completion tracking. Earlier model failures remain preserved.

Observed result: **5/5 passed**, with zero errors or skips; the scoped batch gate
passed. Historical checksums verified unchanged. Combined coverage is now
**50 completed / 48 unfinished** (42 passed and 8 historical quality failures).
The coverage gate remains failing because unfinished cases and prior failures
remain visible; a successful five-case batch does not certify all 98 questions.

## OpenAI readiness attempt

At the user's request, a separate OpenAI attempt was made on 2026-11-08 using
`gpt-4o` through the direct OpenAI endpoint. The model ID corresponds to the
existing `OPENAI_MODEL=openai/gpt-4o` setting with the routing prefix removed;
`gpt-4o` is an alias, not a pinned snapshot.

Evidence is retained in `evals/reports/openai-resume-20261108T161540Z/`.
The single minimal readiness request returned **HTTP 429 after 2.697571 seconds**,
with zero retries and a 30-second per-phase timeout. No timeout occurred.
Readiness failed, so no benchmark cases were run and completion remains
**45 completed / 53 unfinished**. The running Docker provider was unchanged.

The safe saved error does not distinguish rate limiting from exhausted quota;
it provides no confirmed reset time. Check the OpenAI project's limits and
billing/usage before explicitly retrying. No second request was made.
See [OpenAI's error-code documentation](https://developers.openai.com/api/docs/guides/error-codes).

The new directory contains `readiness.json`, an isolated non-secret
`selection.env`, a source snapshot and a SHA-256 manifest. Prior Groq reports
and coverage were copied into `history/` before the probe. Existing historical
reports were not overwritten. A failed readiness attempt is not a benchmark
pass or a completed knowledge case.

## Earlier Groq verification

On 2026-11-08, Groq with `openai/gpt-oss-20b` passed one minimal JSON readiness
request in 17.466309 seconds, with zero retries. It then passed a complete live
knowledge case, including grounded generation and citation validation. This is
evidence of working integration, not sustained capacity or catalog-wide quality.
The running Docker configuration still selects Gemini; this evaluation used an
isolated selector file and did not change either private environment file.

Evidence is saved locally under
`evals/reports/groq-resume-20261108T155939Z/`:

| Case | Result | Recorded boundary |
| --- | --- | --- |
| `tc-045` | Error | Pinecone connection error during retrieval, 3.220784 seconds; no LLM call reached |
| `tc-046` | Passed | Retrieval, relevance grading, answer generation and citation safeguard all completed |
| `tc-047` | Error | Groq HTTP 429 during answer generation |
| `tc-048`, `tc-049` | Skipped | Rate-limit stop; not scored as passes |

For `tc-046`, grading took 0.985616 seconds, generation 1.864473 seconds and
local citation validation 0.001193 seconds. Both model calls used a 30-second
per-phase limit and zero automatic retries. Expectations were unchanged.

The 429 response recorded `retry-after: 6`, request reset `4m19.2s`, and token
reset `44.452s`, relative to its response date, 2026-11-08 16:05:37 UTC.
These historical headers do not guarantee current quota availability. No further
calls were made after that batch. One Pinecone error followed by successful
retrieval on other cases does not establish a persistent outage or its cause.

Combined completion tracking now shows **45/98 completed: 37 passed, 8 failed,
2 errors and 51 skipped; 53 unfinished**. This combines historical attempts from
multiple providers and code versions. It is not a Groq-only quality score.
The new Groq batch itself has 1 pass, 2 errors and 2 skips, so its gate fails.

## Historical reproducibility

- `history/` contains byte-for-byte copies of prior reports, including the prior
  coverage and failed Gemini readiness report. Original report paths were untouched.
- `manifest.json` records historical checksums, source hashes, Git revision,
  dirty state, isolated provider/model selection and source archive checksum.
- `source-snapshot.zip` captures Python source and evaluation catalogs at readiness.
- The first batch launch exposed a float-versus-integer CLI argument bug before
  any benchmark case ran. The corrected code is preserved separately in
  `source-snapshot-benchmark.zip` and `benchmark-source-manifest.json`; the initial
  snapshot remains intact.
- `readiness.json`, `batch-001.json` and `coverage.json` retain actual observations.
  All copied historical checksums were verified after the batch. Evaluation
  expectation hashes are checked before coverage can be combined.
- Source archives contain no environment files or credentials. Reports contain
  no raw policy text, employee information, prompts or raw generated answers.

Live model behavior and a remotely changing Pinecone index cannot be reproduced
bit-for-bit. Chunk hashes identify retrieved evidence without retaining its text;
the source snapshot alone does not reconstruct the remote corpus. Keep snapshots
and failed attempts rather than replacing them with passing reruns.

## Bounded future resume

The batch runner now accepts `--max-batches` and an integer `--timeout`, and stops
before another batch after any recorded error. A 429 stops remaining cases inside
the current batch; other errors are recorded while that batch finishes. Three
offline runner tests pass, including bounded execution, timeout forwarding,
error stopping and preserving seed reports.

After explicitly deciding to resume, run this from PowerShell at the repository
root. It uses the saved non-secret selector and reads credentials privately from
`.env.docker`; it does not change Docker's provider:

```powershell
$env:LLM_ENV_FILE = (Resolve-Path 'evals/reports/groq-resume-20261108T155939Z/selection.env').Path
.venv\Scripts\python.exe -B -c "from dotenv import load_dotenv; import runpy; load_dotenv('.env.docker'); runpy.run_module('scripts.run_knowledge_batches', run_name='__main__')" --exclude-report evals/reports/groq-resume-20261108T155939Z/history/coverage.json --output-dir evals/reports/groq-resume-20261108T155939Z --batch-size 5 --max-batches 1 --delay 10 --timeout 120
```

The runner creates the next unused batch number and skips completed cases,
including quality failures. Errors/skips remain eligible for retry. Before running
changed source, preserve a fresh source snapshot and manifest; the existing
benchmark snapshot identifies the code used for `batch-001`, not future changes.
