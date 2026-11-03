import assert from "node:assert/strict";
import test from "node:test";
import { canUseManualJournal, parseManualJournal } from "../src/manualJournalContract.ts";

const first = {
  id: "9b16f6cf-04b4-4929-a2ee-814050682fd8", revision: 1,
  recorded_at: "2026-11-03T10:00:00+00:00",
  observed_at: "2026-11-03T18:00:00+08:00",
  available_cash: "1234.5600", total_equity: null,
  lots: [{ symbol: "600000.SH", quantity: "100", paid_amount: "980",
    bought_at: "2026-11-02T09:30:00+08:00" }],
  operation: null, note: "", source: "user_manual", realtime: false,
  broker_reconciled: false, full_account_verified: false,
  trade_execution_enabled: false,
};
const good = {
  schema_version: "m8.manual_journal.v1", source: "user_manual",
  notice: "仅为用户手工记录，未与券商核对；不代表实时账户、可卖数量或交易许可。",
  latest_revision: 1, total_revisions: 1, latest: first, history: [first],
  realtime: false, broker_reconciled: false, full_account_verified: false,
  trade_execution_enabled: false,
};

test("accepts a server-synced self-reported revision", () => {
  assert.equal(parseManualJournal(good).latest?.lots[0].paid_amount, "980");
  const unknownBuy = { ...first, lots: [{ ...first.lots[0], bought_at: null,
    paid_amount: null }] };
  assert.equal(parseManualJournal({ ...good, latest: unknownBuy,
    history: [unknownBuy] }).latest?.lots[0].bought_at, null);
});

test("rejects false broker/live/trade claims and private extra fields", () => {
  for (const changed of [
    { ...good, broker_reconciled: true },
    { ...good, realtime: true },
    { ...good, trade_execution_enabled: true },
    { ...good, account_id: "private" },
    { ...good, latest: { ...first, broker_reconciled: true } },
    { ...good, latest: { ...first, raw_broker_row: "private" } },
  ]) assert.throws(() => parseManualJournal(changed));
});

test("rejects inconsistent revisions, invalid values and dates", () => {
  for (const changed of [
    { ...good, latest_revision: 2 },
    { ...good, total_revisions: 0 },
    { ...good, history: [] },
    { ...good, latest: { ...first, available_cash: "NaN" } },
    { ...good, latest: { ...first, lots: [{ ...first.lots[0], quantity: "-1" }] } },
    { ...good, latest: { ...first, observed_at: "2026-02-30T10:00:00+08:00" } },
  ]) assert.throws(() => parseManualJournal(changed));
});

test("allows HTTPS and local loopback HTTP, never LAN plaintext", () => {
  assert.equal(canUseManualJournal({ protocol: "https:", hostname: "192.168.1.10" }), true);
  assert.equal(canUseManualJournal({ protocol: "http:", hostname: "localhost" }), true);
  assert.equal(canUseManualJournal({ protocol: "http:", hostname: "127.0.0.1" }), true);
  assert.equal(canUseManualJournal({ protocol: "http:", hostname: "192.168.1.10" }), false);
});
