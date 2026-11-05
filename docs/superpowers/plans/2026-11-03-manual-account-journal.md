# Manual Account Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-synced, explicitly self-reported manual account journal for infrequent trading, usable from phone and desktop after trusted home HTTPS setup.

**Architecture:** Append-only revision records in PostgreSQL, separate from formal account snapshots and execution fills. A bearer-protected API serves the latest and recent revisions; a React panel holds the token only in memory and posts full revised snapshots with optimistic version checks.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL, React/TypeScript.

**Spec:** [手工账户台账设计](../specs/2026-11-03-manual-account-journal-design.md)

## Global Constraints

- Default disabled; strong token and trusted HTTPS or loopback transport required for both read and write.
- Manual records are separate from formal broker/account/trade models and never authorize trade execution.
- All financial decimal values are exact, finite, non-negative where appropriate; timestamps include timezone and cannot be in the future beyond five minutes.
- No user account identifier, password, PDF, or token in response/logs; no browser token persistence.

## Review Focus

- Concurrent phone/desktop edits: one wins; the other receives a conflict, preserving its unsent form.
- Reload after save: the same latest revision and server timestamp return; no in-memory-only success.
- Invalid or missing access token: no journal data leaks, including count and existence.
- LAN HTTP and forged forwarding headers: reject before reading or writing records.
- A partial sell or missing operation: no automatic claim of broker holdings, current market value, T+1, or full-day completeness.

---

### Task 1: Journal schema and validation

**Files:** `backend/app/db/models.py`, `backend/alembic/versions/0005_m8_manual_account_journal.py`, `backend/app/workbench/manual_journal.py`, `backend/tests/test_manual_journal.py`.

**Interfaces:** `ManualJournalWrite` validates observed time, cash/equity, lots and optional operation. `append_manual_record(session, payload)` checks `expected_revision`, appends revision, and returns an explicit safe response. `read_manual_records(session)` returns latest and recent revisions.

- [ ] Write failing model/service tests for first save, second save, stale version, financial and timestamp validation, and unchanged formal tables.
- [ ] Run focused tests; confirm RED.
- [ ] Add schema, migration, validation, service functions.
- [ ] Run focused tests and migration smoke; confirm GREEN.
- [ ] Commit this slice.

### Task 2: Protected API

**Files:** `backend/app/core/config.py`, `backend/app/main.py`, `backend/tests/test_manual_journal_api.py`, `.env.example`.

**Interfaces:** `GET /workbench/manual-journal`, `POST /workbench/manual-journal`. Both require feature flag, 32+ character bearer token and trusted transport; return only self-reported journal fields and false trade/broker flags.

- [ ] Write failing API tests for disabled, wrong token, weak token, remote HTTP, safe local/HTTPS, and conflict.
- [ ] Run focused tests; confirm RED.
- [ ] Implement protected routes and settings; keep responses and errors free of private content.
- [ ] Run focused tests; confirm GREEN.
- [ ] Commit this slice.

### Task 3: Manual journal page

**Files:** `frontend/src/ManualJournal.tsx`, `frontend/src/manualJournalContract.ts`, `frontend/src/App.tsx`, `frontend/tests/manualJournalContract.test.mjs`, `frontend/src/styles.css`.

**Interfaces:** Tab for latest and historical self-reported records; token in component state; form prefilled from latest revision; explicit full snapshot save; status text never asserts broker verification or live prices.

- [ ] Write failing contract tests for safe schema/provenance, date/number validation, no trade flags, and transport gate.
- [ ] Run focused tests; confirm RED.
- [ ] Implement page and navigation with safe request/response handling.
- [ ] Run frontend tests, typecheck, build; confirm GREEN.
- [ ] Commit this slice.

### Task 4: Final verification and evidence

**Files:** `docs/m8-acceptance-matrix.md`, `docs/m8-manual-journal.md`.

- [ ] Run full backend tests, Ruff, frontend tests, typecheck, build and inspect migration.
- [ ] Review data provenance, privacy, concurrent edits and lack of formal audit promotion.
- [ ] Record local and CI results; keep PR #19 Draft and M8 Gate FAIL.

## Execution ledger

- Ruling: The supplied local checkout is an extracted archive without `.git`; all reviewed changes will be sent as one atomic commit to the existing Draft PR using the GitHub connector and an expected-head lease. The cost is less granular commit history for this slice.
- Ruling: Home Wi-Fi sync requires trusted HTTPS and whole-site access protection, which the current development Compose stack does not provide. The manual journal is disabled by default and phone use remains an acceptance gap. The cost is that the user cannot use phone sync until deployment and device trust are set up.
- Task 1: service/model validation 13 focused tests passed; SQLite Alembic upgrade through revision 0005 passed.
- Task 2: 4 API tests passed; disabled, authentication, transport, save/read/conflict covered.
- Task 3: 4 frontend contract tests, typecheck and Vite build passed; form and readback implemented.
- Final review: two important findings fixed. Trailing-zero Decimal persisted unreadably (regression test RED→GREEN); changing token during pending request left controls stuck (token input now disabled and pending explicitly reset on change).
- Final local verification: backend 590 passed, 4 skipped; Ruff passed; frontend 120 passed, TypeScript and Vite build passed. M8 Gate remains FAIL.
- User refinement: after an initial alignment, each later buy/sell must automatically change lot quantity. Ruling: sell allocates one operation across selected existing lots; partial sell clears remaining paid amount because cost allocation is not known. The cost is an extra user check for each allocation and partial-sale cost.
- Ruling: whole-site Caddy Basic Auth requires `Authorization`; journal uses a separate `X-Workbench-Journal-Token` header. The cost is two passwords to enter, but the whole workbench and manual records are separately protected.
- Ruling: a separate home Compose config exposes only TLS on a chosen LAN IP, runs migration, and keeps backend/PostgreSQL private. The cost is Docker and device CA setup; no deployment or Safari verification can be claimed until the user's host is available.
- Automatic operation verification: backend 604 passed, 4 skipped; Ruff passed; frontend 121 passed, TypeScript and Vite build passed. YAML parse and static port isolation passed; Docker/Caddy runtime unavailable locally. M8 Gate remains FAIL.
- Fresh reviewer found multi-lot and ordered backfill blocking real use, empty-holdings and pre-2000 date contract mismatch, and a read/count race. RED→GREEN tests added for each; one atomic multi-lot operation, chronological backfill after prior operation, explicit empty snapshot, broader timestamp parsing and coherent single-read count implemented.
- Final reviewer found signed-zero fee could make a saved revision unreadable. RED→GREEN test added and zero serialization normalized. Outdated multi-lot docs corrected.
- Final local verification: backend 612 passed, 4 skipped; Ruff passed; frontend 125 passed, TypeScript and Vite build passed. Home YAML and port isolation static check passed. Docker/Caddy runtime and real Safari remain unverified; M8 Gate FAIL.
