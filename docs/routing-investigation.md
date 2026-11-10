# Offline routing investigation: tc-014 and tc-043

Reviewed on 2026-11-10. No live requests were made for these cases. Neither
catalog entry nor its expectation hash changed. The historical full score
remains **83 passed / 15 failed**, with zero errors or skips.

## Preserved evidence

Original batch-report copies, a scoped original report, source hashes and five
content-free controlled traces are in ignored
`evals/reports/routing-offline-20261110T093714Z/`. `manifest.json` records checksums.
The frozen 98-case JSON retains SHA256
`40ce2942e2b19d68c35c5d89c9982a49c0bd4884a9ca6830608555bea007d620`.

| Case | Unchanged expectation hash |
| --- | --- |
| tc-014 | `183573c54df91dbb605d117692ec773474346d91a03c58b75d36993618d41a67` |
| tc-043 | `b3cfe17ff6eb508ffb713ce04344207f58efc5572ffecaa99e0684f11a6dd779` |

Historical reports retain statuses, document IDs and check outcomes, but not the
original supplied chunks, grader decisions or candidate answers. The scenarios
below reproduce possible boundaries, **not the lost historical execution**.

## Pipeline boundary

Retrieved chunks go to relevance grading. A positive grade proceeds directly to
internal generation and citation validation. Classification runs only after a
negative grade: public technical questions can use web search; company-specific
gaps receive clarification. It is not an independent decision before every answer.

## tc-014: local internet troubleshooting

“Why is my Wi-Fi connected but there is no internet access?” requires
`answered_web` in the benchmark. Historically it returned `answered`, cited VPN
guidance and bypassed classification. Only the status check failed.

[VPN sections 4.1 and 4.2](../data/knowledge_base/vpn_troubleshooting.md) contain
applicable local-network, public-site and captive-portal checks. Supplying that
actual chunk with a mocked positive grade produces a valid internal answer and
fails only the unchanged web-status expectation. A negative grade followed by
public classification passes the original case through the web route.

This exposes a tension between internal-first behavior and a benchmark requiring
web routing. The historical result alone does not establish a factually wrong
answer, nor prove the old candidate adequate. **No expectation revision is made.**
A later review must decide whether public routing itself is a product requirement
or whether quality should be route-independent, before a separate revision.

## tc-043: company VPN port

“Which port does the VPN use?” requires an internal answer citing `KB-NET-0042`
and stating `443`. Historically that document was retrieved, but the result was
`answered_web` / `general_technical` with public citations. Status, category and
expected-document citation failed.

[VPN section 2](../data/knowledge_base/vpn_troubleshooting.md) explicitly states
TCP and UDP 443 outbound. Supplying its actual chunk and accepting it passes the
original contract. Rejecting that same useful chunk and taking the public route
recreates exactly the historical failed-check set. A separate introduction chunk
from the same document lacks the port fact: document recall alone cannot prove
that sufficient evidence reached generation.

The original expectation remains justified. Saved evidence cannot distinguish
retrieval of the wrong section from grader rejection or classification error.
Generic query expansions could add noise, but are not a proven historical cause.
No speculative retrieval/routing, timeout or citation-safeguard change is made.

## Verification and next evidence

Six tests in `tests/test_routing_investigation.py` exercise the compiled graph,
local chunks, prompts and scorer with mocked provider responses and a network
tripwire. They check content reaches grading/generation, classification bypass,
content-free serialized diagnostics and both original hashes. Offline CI includes
them. The full suite passed **177 tests**, and the separate provider-mocked
runtime scorecard passed **20/20**. Scripted success is not live-model success.

A future targeted run should retain these originals and record current chunk
hashes, grade, route and safeguard reason. New outcomes must remain separate.
No full benchmark or automatic run was started.

## Final Docker smoke

`python -B scripts/verify_compose.py --live-model --credential-contract` exited 0
on 2026-11-10. Real setup/login, employee/admin credential refusals, admin mutation
denial, MCP device/ticket operations, pre-review editing, queue versus detail
locks, admin resolution, employee closure/history, and logout revocation passed.
A live model identity lookup traversed LangGraph/MCP/REST/PostgreSQL; chat history
was restored after a fresh login. Temporary business records and conversation
threads created by this run were cleaned up. Existing volumes were retained.
This scoped smoke is not a fresh knowledge benchmark.

README screenshot capture was attempted, but Computer Use stopped because it
could not confidently determine the browser URL. No screenshots were fabricated
and no alternate UI automation bypass was attempted.
