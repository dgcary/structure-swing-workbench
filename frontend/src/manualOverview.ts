import type { ManualJournalRecord } from "./manualJournalContract";

export function summarizeManualAccount(record: Pick<ManualJournalRecord,
  "observed_at" | "available_cash" | "total_equity" | "lots">) {
  return {
    observedAt: record.observed_at,
    availableCash: record.available_cash,
    totalEquity: record.total_equity,
    stockCount: new Set(record.lots.map((lot) => lot.symbol)).size,
    lots: record.lots,
  };
}
