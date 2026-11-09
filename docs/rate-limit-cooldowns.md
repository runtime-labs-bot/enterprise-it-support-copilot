# Respecting provider reset windows

Evaluation resumption now uses the **latest valid deadline** from these saved
headers, rather than relying only on `retry-after`:

- `retry-after` (seconds or an HTTP date)
- `x-ratelimit-reset-requests` (duration)
- `x-ratelimit-reset-tokens` (duration)

Durations support fractional seconds and composite units such as `7m12s`,
`53.79s`, `1h2m3s`, and milliseconds. The provider response `date` anchors relative
intervals. If absent, the original report observation time is used conservatively.
An old interval is never restarted from the current resume time. Invalid values
are ignored; missing timing evidence does not imply readiness or invent a midnight
daily reset. Without remaining-quota counters, considering all valid reset headers
is a conservative policy, not evidence that every quota was exhausted.

## Saved Groq example

Batch 007 recorded a 429 at **2026-11-08 17:25:00 UTC**, with:

| Header | Saved interval |
| --- | --- |
| `retry-after` | 1 second |
| Request reset | 7 minutes 12 seconds |
| Token reset | 53.79 seconds |

The conservative not-before time is therefore **17:32:12 UTC / 23:02:12 IST** on
November 8. At 17:26 UTC, 372 seconds remain; at the deadline, the cooldown expires.
This is a historical computed window, not a guarantee that a future call succeeds.
No provider requests were made to implement or test this change.

## Enforcement

The batch runner checks its seed and prior batch reports before starting. The
scorecard also checks prior batches in its output directory before creating any
workers. A live rate-limit result now retains a safe `retry_window` alongside the
existing allowed header fields. Completed outcomes and historical files remain
unchanged.

Checks are provider-scoped: a Groq cooldown does not block Gemini. Coverage report
references and prior cooldown reports are followed back to the original evidence,
so using a coverage seed or moving to a new output directory need not lose the
original deadline. If reports are relocated, keep referenced evidence accessible.

Both the scorecard and readiness CLI accept repeatable `--rate-limit-report PATH`
arguments to supply prior evidence outside their output directory. For example,
append this option to the next invocation:

```text
--rate-limit-report evals/reports/gemini35-remaining-20261108T170129Z/coverage.json
```

When a known window is active, the runner exits without live calls. The scorecard
records skipped cases with the deadline and remaining wait; readiness records
`ready: false` without making a request. This does not sleep for minutes, silently
retry, schedule automatic resumption, or count skipped cases as passes. Once the
window expires, an explicitly requested invocation may proceed normally.

Provider selection still must be set explicitly for readiness/evaluation. The
check is based on saved evidence for that provider, not a fresh quota inspection.
Different accounts on the same provider conservatively share the report's gate;
no credential identifiers are stored to distinguish them.

## Verification

All **152 root offline tests passed**, including nine new tests for longest-window
selection, fractional/composite durations, HTTP dates, elapsed time, expiry,
provider isolation, nested report references, invalid evidence, and preventing
readiness/worker calls while a window is active. The new test file is included in
the offline GitHub Actions workflow; this local change has not been pushed.

No live cases were resumed. Coverage remains **75 completed / 23 unfinished**.

## Subsequent pacing correction

The November 9 resume selected 60 seconds between live cases. The parent runner
now also applies that configured delay **between batches**, where the worker's
within-batch delay previously did not apply. Nine batch-runner tests passed after
the correction. The original nine cooldown tests and 152-test result above
describe the earlier implementation verification, not a new live run or rerun of
the full suite. See the [current progress](expanded-evaluation-progress.md) for
the latest coverage and saved cooldown deadline.
