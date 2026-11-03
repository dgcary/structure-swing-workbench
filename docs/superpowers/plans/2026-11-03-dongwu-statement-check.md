# Dongwu Statement Read-Only Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify internal consistency of a Dongwu Xiucai PDF statement without treating it as live, complete broker fills.

**Architecture:** Parse the statement in memory through `pdfplumber`, recognize its summary and detailed execution tables by headers, repair the three possible first rows whose PDF cell geometry omits right-side cells, then compare date/exchange/currency/side/symbol groups using exact `Decimal` quantities and fees. Return counts and limitations only; retain no customer data and expose no trade order endpoint.

**Tech Stack:** Python 3.12, pdfplumber, pytest, Decimal.

**Spec:** `docs/m8-dongwu-broker-intake.md`, `docs/m8-acceptance-matrix.md`, and `docs/trading-rules.md` §10–11.

## Global Constraints

- No original PDF, password, customer identifier, security code, price, quantity, or balance in Git or test fixtures.
- No invented execution ID, execution time, timezone, or current price.
- `broker_reconciled=false`, `full_account_verified=false`, `trade_execution_enabled=false` for every result.
- Keep PR #19 Draft and M8 Gate FAIL.

## Review Focus

- A page-break row whose right-hand cells are visually present but omitted by `pdfplumber` must be recovered from the PDF page before comparison.
- A true missing summary group or altered amount/fee must produce a mismatch, not a clean result.
- Unsupported PDF headers and unreadable rows must fail closed.
- The statement may combine account types; a row cannot become a confirmed A-share execution without an independent identity and account scope check.
- Date-only rows cannot become timestamped `ExecutionFill` facts or a T+1 ledger.

---

### Task 1: Pure statement group comparison

**Files:** Create `backend/app/workbench/dongwu_statement.py`; create `backend/tests/test_workbench_dongwu_statement.py`.

**Interface:** `compare_statement_rows(summary_rows, detail_rows, *, period_start, period_end, repaired_rows) -> StatementCheck` accepts already extracted 11- and 14-column rows, returns counts and a safe status.

- [x] Write failing tests for grouped exact quantity, amount, commission, stamp and transfer checks, plus missing/changed rows and invalid period.
- [x] Implement strict header, date, decimal and side validation; compare groups without exposing values in result.
- [x] Run focused tests and Ruff.

### Task 2: PDF table extraction and cross-page recovery

**Files:** Modify `backend/app/workbench/dongwu_statement.py`, `backend/tests/test_workbench_dongwu_statement.py`, `backend/pyproject.toml`.

**Interface:** `check_dongwu_statement_pdf(data: bytes) -> StatementCheck` finds tables by header and repairs cells with missing geometry using the next complete row's x bounds and current row's y bounds.

- [x] Add synthetic PDF tests for good, missing and unsupported tables, including a page-break-shaped row with absent cell geometry.
- [x] Add `pdfplumber` to a broker PDF extra and dev test environment; implement extraction with size and page caps.
- [x] Run backend tests and Ruff: 562 passed, 4 skipped; Ruff passed locally.

### Task 3: Real statement validation and evidence update

**Files:** Modify `docs/m8-dongwu-broker-intake.md`, `docs/m8-acceptance-matrix.md`.

- [x] Run the checker only in memory on the user-supplied encrypted ZIP, entering its password interactively and printing safe counts/status only.
- [x] Record result, the statement's prior-trading-day holdings scope, and the missing execution ID/time limitation without copying private values.
- [ ] Run full backend suite and update Draft PR; verify CI and TSK-18 evidence.

## Execution ledger

- Ruling: Account, holdings and cash-flow tables before the trade headers are ignored because the statement contains distinct non-trade sections; a dated row with changed width after trade parsing begins is rejected. If this boundary is wrong, a future broker layout may need a new parser version.
- Ruling: The PDF's typed currency totals are recognized by exact column occupancy and numeric cells, and are not treated as executions. If their layout changes, parsing fails closed until reviewed.
- Final review: a fresh reviewer found three Important false-match paths (incomplete header checks, changed later headers, and skipped damaged rows). Each was reproduced with a failing synthetic test, fixed, and covered by the 562 passed / 4 skipped full suite.
