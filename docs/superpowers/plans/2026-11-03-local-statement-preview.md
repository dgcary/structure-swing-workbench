# Local Dongwu PDF Preview Plan

**Goal:** Let the user check an extracted Dongwu statement PDF from the Web workbench without broker login, persistence, or live account promotion.

**Scope:** Add an opt-in API that accepts PDF bytes only when the backend is configured to listen on loopback; stream with a 10 MB cap, invoke the existing in-memory checker, and return safe aggregate counts. Add a Chinese UI upload panel with explicit local-only and historical-data language. The user extracts the ZIP on their device; its password is never sent to the app.

**Safety contract:** Disabled by default. No broker account API, raw rows, file contents, password, execution IDs, account values, or trade orders in the response or logs. A successful check remains `matched_unverified`, `broker_reconciled=false`, `full_account_verified=false`, `trade_execution_enabled=false`. Never place the result into the live overview metrics or persist it.

## Tasks

1. Add failing API tests for disabled-by-default, non-loopback rejection, capped streaming, bad PDF, and aggregate-only response. Implement config and route.
2. Add a pure frontend response validator and tests for safe flags, counts, dates, impossible statuses and private-value fields. Implement a standalone `DongwuStatementPreview` panel under the existing local import disclosure.
3. Run backend and frontend suites and builds. Review the change for information leaks and false account certification. Update the M8 acceptance matrix and keep PR #19 Draft.

## Rulings

- The existing parser accepts PDF bytes, so the UI requires the user to extract the PDF from the encrypted ZIP locally. This avoids receiving the ZIP password and limits the new feature to one file format.
- The backend must be explicitly bound to `localhost` or a loopback address before this upload route can be enabled. A reverse proxy or container bound to `0.0.0.0` cannot use this local-only feature without a separate security design.
- An independent review found that `/api` could point to a configurable remote proxy. PDF upload now uses a fixed `http://127.0.0.1:8000` endpoint directly; local CORS preflight is tested. Another review found that `asdict` could expose future private parser fields. The response now uses an explicit safe-field allowlist, with a regression test.

## Verification

- Backend: 573 passed, 4 skipped; Ruff passed.
- Frontend: 116 passed; TypeScript and Vite build passed.
- M8 remains unaccepted: this only checks statement internal consistency, without broker completeness, current account state, or trading permission.
