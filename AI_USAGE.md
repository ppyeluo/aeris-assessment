# AI tool usage disclosure

The brief allows AI-assisted tools **provided their use is disclosed and every
submitted decision can be explained**. This file is that disclosure.

## Where AI assistance was used

1. **Design discussion.** Working through the state model for Task A (what "refused
   operations are still processed" implies), the three-level comparison order and DP
   shape for Task B, and the concurrency/idempotency approach for the app.
2. **First-draft code.** The initial version of `A/solution.py`, `B/solution.py`, the
   FastAPI service, the React components, and the test suites were drafted with AI
   assistance, then reviewed and adjusted.
3. **Research for Task C.** Locating the current official Xero documentation and the
   published OpenAPI specification, and extracting the rate-limit numbers, pagination
   behaviour, `If-Modified-Since`, `Idempotency-Key` and `xero-tenant-id` details.
   All five cited links were checked and return HTTP 200.
4. **Documentation.** Wording of the READMEs, `C/answers.md` and this file.

## What was verified independently (evidence)

* Every command in the root README was executed locally, in the order given.
* Test suites: **24 (A) + 23 (B) + 21 (backend) + 23 (frontend) = 91 tests, all passing.**
* Both worked examples from the brief are reproduced **byte-for-byte** by the programs
  (`diff` against `samples/sample1.out` is empty).
* Task B's optimiser was cross-checked against an exhaustive brute-force reference on
  **400 fixed-seed random instances** — this is what confirmed that the lexicographic
  tie-break must compare lists **after** sorting by `warehouse_id`.
* The app was started for real (uvicorn + Vite) and exercised over HTTP: catalogue
  fetch, add-to-cart with and without an idempotency key, replay of the same key,
  insufficient stock (`409`), cart totals, static images, and the Vite → FastAPI proxy.
* The Xero figures used in Task C were read from the official FAQ page text and the
  OpenAPI specification (`Xero-OpenAPI`, Accounting API 19.1.0) rather than from
  memory; anything not stated there is marked as an assumption in `C/answers.md`.

## What remains the candidate's own judgement

The assumptions listed in the root README (the `OPEN` line format, the lexicographic
reading of the allocation list, `fixed_cost` semantics, idempotency-key reuse, cart
reservation semantics) are deliberate readings of an intentionally open brief. They were
chosen and reviewed by the candidate, not generated.

## Statement

No credentials, tokens or real customer data appear anywhere in this repository. Every
file here is intended to be walked through, explained and modified live during the
follow-up interview.
