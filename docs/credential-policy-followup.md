# Credential response contract and policy coverage review

The tested provider/evaluation changes were pushed as `dbe841a`.
[Its hosted offline CI passed](https://github.com/rushberry02/enterprise-it-support-copilot/actions/runs/42673552400).
Docker Desktop was started, all Compose services were rebuilt and became healthy,
and migrations completed. No persistent database or chat volumes were removed.

The initial deployed checks passed login/setup, permissions, ticket editing/review
locks, real MCP ticket operations, logout revocation, employee isolation and
concurrent creation idempotency. Temporary business records were cleaned up.
The deployed citation code matched local source hashes and passed five renderer
tests plus ten citation-guard checks, with model networking mocked.

## `tc-098`: stable refusal before tools

The historical `answered` status did not establish credential disclosure. A new
regression demonstrates that a harmless policy refusal can fail that old response
contract solely because of its status and source cards. No historical raw answer
was retained, so that result is not described as a leaked password.

The graph now begins with a credential-response boundary, before MCP, retrieval
or any model. Matched requests for secret values and secret offers receive a
fixed, source-free refusal. It tells users not to paste secrets and asks only
about their non-secret sign-in/access problem. It does not ask which password,
token or code to supply, echo a submitted value, or prepare an admin action.
The existing `insufficient_context` status is retained for compatibility;
`credential_request_blocked` distinguishes this deliberate refusal internally.

Both employee and admin chats follow this path. The guard clears stale source,
generation and proposal state; it resets on a subsequent legitimate request.
Matched prior human messages are withheld from future retrieval and MCP model
context. Password reset, password-policy and normal authenticated device queries
retain their regular routes. The catalog's policy questions `tc-025`, `tc-030`
and `tc-042` were specifically checked to avoid mistaking policy discussion for
a request to retrieve a secret.

Ten offline credential-contract tests cover designed requests/offers, common
Unicode/identifier forms, follow-ups, history, both roles, normal operations and
the unchanged `tc-098` expectations. A separate compiled-graph check passed
`tc-087`, `tc-090` and `tc-098` with **zero provider calls** and no regressions.
All provider/retrieval stages were `not_run`, as intended.

This is a bounded text guard with model-instruction and backend-permission
defenses, not proof that every language or encoding is understood. It does not
erase previously stored chat text or change the trusted login/setup forms.
The contract covers the assistant answer and external context; the API still
returns the user's submitted question in its normal response envelope.

## `tc-054` / `tc-072`: sufficient evidence, rather than document count

Semantic source review found that
[VPN policy section 6](../data/knowledge_base/vpn_troubleshooting.md#6-security-rules-during-troubleshooting)
independently supports both answers:

- For `tc-054`, it explicitly prohibits free/third-party VPN workarounds.
- For `tc-072`, it prohibits internet installation and requires Company Portal.

The software policy corroborates these restrictions. It is not necessary as a
second citation when the applicable VPN section is already cited. Requiring both
documents penalized a sufficient single-source answer; the model was not forced
to add a citation merely to pass.

Only these two catalog entries have an explicit **expectation revision 2**.
`evals/expectation_reviews.json` records the previous catalog commit, old hashes,
source section and rationale. The required source remains the VPN document;
valid citations and the answer status are still mandatory. New lexical checks
require the restriction to be expressed; `tc-072` also names Company Portal.
Controlled wrong-policy answers and unknown citations still fail. Lexical checks
are not a semantic entailment judge.

The two v2 cases passed a targeted Gemini 3.5 Flash-Lite run. This is validation
against reviewed expectations, **not an unchanged-expectation score improvement**.
The evaluator rejects old/new baseline compatibility for these changed hashes.
The old 98-case reports remain byte-for-byte unchanged at **83 passed / 15 failed**;
their expectations are recoverable from Git commit `dbe841a` and source snapshots.
No full 98-case run or historical rescoring was performed.

The separate results are under
`evals/reports/gemini35-remaining-20261108T170129Z/credential-policy-review-20261110T055714Z/`.

## Verification and deployment

- **171 unit tests passed**, plus **20/20** scripted runtime checks.
- The two reviewed policy cases passed a focused live run; credential checks
  did not call a provider.
- Docker now selects the validated `gemini-3.5-flash-lite` model rather than the
  earlier `gemini-3.8-flash` selection. Private keys were preserved.
- The deployed credential source hashes matched local files, and all ten
  credential tests passed inside the container with zero provider calls.
- Authenticated employee/admin HTTP checks passed secret requests, follow-ups
  and offers without echoing values or producing pending actions. Normal MCP,
  ticket workflows, permissions and revocation also passed again.
- Temporary credential-test checkpoint threads and business fixtures were
  removed. Sanitized container evidence is in
  `evals/reports/docker-credential-contract.json`.

To repeat the deployed checks without live model calls:

```bat
.venv\Scripts\python.exe -B scripts\verify_compose.py --credential-contract
```

CI includes both new offline test files. Remaining work is routing/expectation
review for `tc-014`/`tc-043`, then separately preserved targeted checks of the
other known web and legacy failures. No automatic evaluation is scheduled.
