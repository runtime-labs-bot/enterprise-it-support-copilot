# Offline review of expanded evaluation failures

This review uses the preserved `evals/reports/expanded-initial/batch-001.json`
and `batch-002.json`, the case catalog, local knowledge documents and application
code. No new model, retrieval or web-search requests were made for this review.
Historical failures and expectations remain unchanged.

| Case | Saved evidence | Diagnosis and remaining uncertainty |
| --- | --- | --- |
| `tc-008` | Status `answered`; expected `KB-SW-0008` retrieved; all three citation checks false | Retrieval coverage passed, but no supported inline labels were recognized. The original raw answer and finish reason were not retained, so omission, an unsupported label style and truncation cannot be distinguished. |
| `tc-013` | Status `answered_web`; category `general_technical`; both citation checks false | Routing/classification succeeded. Attribution recognition failed after generation; the report cannot establish the precise output format or whether the answer was truncated. |
| `tc-014` | Status `answered` instead of `answered_web`; valid citations to `KB-NET-0042`; classification was not run | The graph chose the internal route because retrieval was graded relevant. This is a route-expectation mismatch, not evidence by itself that the answer's facts were wrong. |

For `tc-008`, the local software document actually contains the request procedure
for software not offered in Company Portal (section 5). The saved retrieved/cited
recalls are 1.0/0.0. There is no evidence of a missing policy document.

For `tc-014`, sections 4.1 and 4.2 of
[`vpn_troubleshooting.md`](../data/knowledge_base/vpn_troubleshooting.md)
explicitly address internet connectivity and Wi-Fi captive portals. That overlap
can explain why the relevance grader accepted internal context for “Wi-Fi
connected but no internet.” The current graph deliberately skips classification
when retrieval is relevant. Before changing routing or the expected route, review
the actual answer in a later diagnostic run against those sections. Do not force
web search solely to make this case pass or weaken its expectation silently.

The generation code previously returned `answered`/`answered_web` regardless of
whether citations were present. The new guard rejects missing or out-of-range
labels and non-`stop` completions; it returns a clarification request with no source
cards and status `insufficient_context`. This prevents unsupported success claims
but does not prove these live cases will now pass. Unit tests cover the guard;
live rechecks are deferred.

## Provider reset and resumption

The saved rate-limit outcomes contain `RateLimitError` and `provider_limited=true`
but no HTTP reset headers or raw response body. Their timestamps are not reset
times. The Groq dashboard check was blocked because browser automation could not
verify the current URL. **The quota reset time is unknown.** No live evaluation
should run until provider availability/reset is confirmed; no background resume
or scheduled model calls have been started.

After confirming availability in the Groq dashboard, resume explicitly in batches
of five (ten is also supported):

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python.exe -B scripts\run_knowledge_batches.py --exclude-report evals/reports/citation-parser-five.json --output-dir evals/reports/expanded-initial --batch-size 5 --delay 10
```

The runner preserves completed failures for review and retries unfinished errors
and skips. Recheck the three failed cases separately after collecting diagnostic
evidence; do not overwrite their original reports.
