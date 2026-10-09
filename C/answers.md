# Task C — Xero Integration Review

**Assumptions and references.** This review covers the Xero Accounting API v2.0 using the
official OpenAPI specification (`XeroAPI/Xero-OpenAPI`, version **19.1.0**) and the
official developer documentation listed at the end of this file. Where the docs do
not state a behaviour, it is marked as an assumption rather than presented as fact.
The service is multi-tenant: every connected organisation has its own tokens, its
own `tenantId`, and its own sync cursor.

---

## C1 — Connection verification

The smallest sequence that *proves* OAuth and tenant selection work before any
invoice is read. Each step has one job, and a failure at each step means something
different.

| # | Call | Assertion | What a pass proves |
| --- | --- | --- | --- |
| 1 | `POST https://identity.xero.com/connect/token` with `grant_type=refresh_token` | `200` + `access_token` + `expires_in` | The stored refresh token is still valid, the client credentials are correct, and the identity service is reachable for this client. |
| 2 | `GET https://api.xero.com/connections` with `Authorization: Bearer <token>` | `200`, and the target `tenantId` is present in the list | The token is authorised for *that* organisation. This is the check that catches "a valid token, but for a different tenant". |
| 3 | `GET /api.xro/2.0/Organisation` with header `xero-tenant-id: <tenantId>` | `200` and `Organisation.Name` matches the expected organisation | The tenant header is accepted, the connection has not been revoked, and the token carries at least `accounting.settings.read`. |
| 4 | `GET /api.xro/2.0/Invoices?page=1&pageSize=1` with the same tenant header | `200` | The `accounting.transactions` / `accounting.transactions.read` scope is genuinely present — this is the permission invoices actually need, so it must be proven with an invoice call, not inferred from step 3. |

Reading order matters: step 4 is deliberately *one page of one record*. It proves
the scope without spending daily quota on a real sync.

Interpretation of failures: step 1 failing is an identity/credential problem;
step 2 failing means the organisation is no longer connected; step 3 failing with
a valid token points at a scope or tenant-header problem; step 4 failing while
step 3 passes isolates the missing scope to transactions.

---

## C2 — Failure diagnosis

The connections call succeeds but `/Invoices` returns 401, 403 or 404 in different
environments. Decision tree:

### 401 Unauthorized — "this token is not acceptable"

1. Is the access token expired? Compare `expires_at` with a **server clock**
   (NTP-synced); refresh proactively ~60 s before expiry. Do **not** retry the same
   token.
2. Refresh once. If the refresh fails → the user revoked the app or the refresh
   token was rotated and the stored one is stale → mark the connection
   `needs_reauthorisation`, stop syncing that tenant, alert.
3. If the refresh succeeds but the new access token still gets 401, suspect
   concurrent refreshes racing (two workers), a wrong `Authorization` header
   shape, or credentials from the wrong environment.

### 403 Forbidden — "the token is fine, the permission is not"

1. Decode the access token's `scope` claim and compare with the scopes the endpoint
   requires (`accounting.transactions` or `accounting.transactions.read`).
2. If the scope is missing → the stored grant was created before the scope was
   added → require re-consent (scopes cannot be added to an existing grant).
3. If the scope is present, the app is not authorised for that organisation
   (the user can disconnect it from *Settings → Connected Apps*), or the endpoint
   belongs to a different product (Payroll/Files) that was never consented.

### 404 Not Found — "the resource or the path is wrong"

1. Wrong `tenantId`: re-read `GET /connections` and compare the id used against
   the stored mapping (a common cause is copying a tenant id between environments).
2. Wrong base URL or path: verify `/api.xro/2.0/...` (not the older
   `/api.xro/2.0/Invoices/{id}` shape for a list call) and the API version.
3. The organisation was disconnected/deleted, or the app's access to it was removed.

**Environment separation.** Each environment (dev/staging/prod) usually has its own
Xero app: different `client_id`, `client_secret`, redirect URI, and — importantly —
its own tenant mapping. Most "works in dev, fails in prod" cases are a tenant id or
client credential from the wrong environment, so the diagnostic output should always
state which environment and which `tenantId` were used.

---

## C3 — Incremental synchronisation

Design for a large organisation, assuming the Accounting API invoices endpoint
(pagination is supported on invoices, contacts, bank transactions and manual
journals; **up to 100 records per call with line items**).

**Cursor.** Per tenant, persist a cursor of the form
`(last_success_utc, last_invoice_id)`, plus `sync_run_id` and `state`.

**Read loop.** `GET /Invoices?If-Modified-Since=<cursor_utc>&page=N` (the header
returns records *created or modified* since the timestamp). Walk pages until a page
returns fewer than `pageSize` records or an empty page. Process each page with an
**idempotent upsert keyed on `InvoiceID`**, so a record appearing twice (page
boundary drift, overlapping window) is harmless.

**Cursor advancement.** Only advance after the whole run succeeds, or — when a run
can span many pages — commit page by page *and* keep a "lowest incomplete page"
marker so a restart resumes rather than re-reads. Never advance on a failed page.

**Change window overlap.** Because `If-Modified-Since` compares timestamps, a record
modified at the same instant as the cursor can be skipped. Re-read a small overlap
window (e.g. cursor minus 5 minutes) every run; the upsert makes the duplicates free.
For very large organisations, prefer multiple narrow windows (e.g. month by month)
over one wide query, so a failure costs one window rather than the whole history.

**Partial failure.** A page that fails (429/5xx) does not advance the cursor. The
run is resumable; retries re-read the same window and converge thanks to the upsert.

**Deletions/archival.** `If-Modified-Since` surfaces modifications, not deletions.
Assumption: archived/voided invoices (available with `includeArchived=true` or via
status) are treated as updates; genuine deletions are not observable through this
endpoint and would need webhooks or a periodic full reconciliation.

---

## C4 — Rate limits

Confirmed limits per tenant: **5 concurrent calls**, **60 calls per minute**,
**5000 calls per 24 hours**; across all tenants the app may make
**10,000 calls per minute**. Every response carries remaining-quota headers
(`X-MinLimit-Remaining`, `X-DayLimit-Remaining`, `X-AppMinLimit-Remaining`).
Exceeding a limit returns **HTTP 429**, and the response includes a `Retry-After`
header in seconds.

**On 429:**

1. Sleep for `Retry-After` if present; otherwise exponential backoff
   (`base * 2^attempt`, capped) with **full jitter** to avoid synchronised retries
   across workers.
2. Treat the call as *not executed* — do not advance the cursor.
3. Keep a per-tenant concurrency of 1–2 in-flight requests (well under the limit of
   5) and serialise work per tenant in a queue, so one organisation cannot starve
   the others.
4. Maintain a token-bucket rate limiter per tenant (start below 60/min) and a daily
   budget (e.g. stop scheduling bulk work at ~4500 calls/day, leaving headroom), and
   adjust using the remaining-quota headers.
5. Schedule bulk syncs off-peak and spread them across the day; prioritise tenants
   whose windows are small.

**Retry policy.** Retry only idempotent/safe operations on 429, 500, 502, 503, 504,
with a bounded attempt count and total time budget. **Do not retry:** 400/422
(malformed or invalid data), 401 (after one refresh attempt), 403 (permission),
404 (wrong resource/tenant), 409 (a business conflict that needs human or explicit
resolution), and never blindly retry a non-idempotent `POST` that timed out — query
first (see C5).

---

## C5 — Data integrity

Creating an invoice is not naturally idempotent, so an internal order retried after
a timeout can duplicate. Two defences, used together:

1. **`Idempotency-Key` request header** (max 128 characters) — present in the official
   specification on the create endpoints. The key is derived deterministically from
   the internal order, e.g. `invoice:{order_id}:v{payload_version}`, so retries of the
   same intent reuse the same key and cannot create a second invoice.
2. **Business-level uniqueness** — Xero enforces invoice-number uniqueness (the API
   returns a `"Invoice # must be unique."` validation error). Map the internal order
   to a deterministic `InvoiceNumber`, and before creating, look it up with
   `GET /Invoices?InvoiceNumbers=...`. If it already exists, adopt it instead of
   creating.

**State machine.** Keep a local table
`invoice_sync(order_id, xero_invoice_id, status, idempotency_key, attempts, last_error,
updated_at)` with `pending → in_flight → confirmed | needs_review`.

**Timeout with unknown outcome.** Mark the row `in_flight` with the attempt time
*before* the request. On recovery, do **not** blindly re-POST: query by
`InvoiceNumber` (or reconcile by the idempotency key) and then either
(a) adopt the existing invoice and mark `confirmed`, or (b) create it again with the
same `Idempotency-Key`.

**Reconciliation.** A scheduled job scans `in_flight` rows older than a threshold,
queries Xero, and resolves them; anything unresolved after N attempts becomes
`needs_review` and raises an alert. Counters for created-vs-adopted invoices expose
duplicate pressure over time.

---

## C6 — Observability and security

**Structured logs** (one JSON object per event) with: `ts`, `level`, `service`,
`env`, `tenant_id`, `connection_id`, `sync_run_id` (the correlation id threaded
through every call in a run), `order_id` / `invoice_id`, `endpoint`, `http_status`,
`latency_ms`, `retry_attempt`, `rate_limit_remaining_{min,day}`, and
`cursor_before` / `cursor_after`.

**Metrics**: sync run duration and records processed; `http_429_total`; auth and
token-refresh failure counts; **sync lag** (now − max `UpdatedDateUTC` seen, per
tenant); in-flight invoices awaiting reconciliation; daily quota consumed per tenant;
last successful sync timestamp.

**Alerts**: repeated 401/403 for a tenant (connection needs re-consent); 429 rate
above a threshold; sync lag beyond SLO; in-flight invoices unresolved past the
reconciliation window; quota consumption that will exhaust the daily limit.

**Never logged** (or logged only as an opaque id): access and refresh tokens, client
secrets, the raw `Authorization` header, full request/response bodies (they contain
customer PII and financial data), contact emails/phones, bank account numbers.
Correlation ids must never be the secret itself.

**Storage and rotation**: tokens live in a secrets manager / encrypted column keyed
by tenant, encrypted at rest, readable only by the sync workers (least privilege,
audited access). Scopes are minimised (read-only where no write is needed). Access
tokens are short-lived and refreshed proactively; note that a refresh **rotates the
refresh token**, so the replacement must be persisted atomically (per-tenant lock) or
concurrent refreshes will invalidate each other. Application credentials are rotated
on a schedule with a documented re-consent runbook, and revocation is verified by an
alert on the next sync attempt.

---

## References

* Xero API limits — FAQ: <https://developer.xero.com/faq/limits>
* OAuth 2.0 API limits: <https://developer.xero.com/documentation/guides/oauth2/limits/>
* Accounting API — Invoices: <https://developer.xero.com/documentation/api/accounting/invoices>
* Idempotent requests (data integrity):
  <https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/>
* Official OpenAPI specification (Accounting API 19.1.0):
  <https://github.com/XeroAPI/Xero-OpenAPI>

**Stated assumptions**: Accounting API v2.0 with OAuth 2.0 authorization-code +
refresh-token grants; an official or first-party HTTP client is used; the rate-limit
numbers and the `Idempotency-Key` / `If-Modified-Since` semantics above were checked
against the official OpenAPI specification (19.1.0) and the FAQ. The exact retention
window of an idempotency key is not stated in the specification reviewed, so this
design does not depend on it — the `InvoiceNumber` check remains the backstop.
