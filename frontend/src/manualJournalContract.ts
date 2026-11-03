export type ManualJournalLot = {
  symbol: string; quantity: string; paid_amount: string | null; bought_at: string | null;
};
export type ManualJournalOperation = {
  side: "BUY" | "SELL"; symbol: string; quantity: string; price: string;
  executed_at: string; fee: string | null;
};
export type ManualJournalRecord = {
  id: string; revision: number; recorded_at: string; observed_at: string;
  available_cash: string | null; total_equity: string | null;
  lots: ManualJournalLot[]; operation: ManualJournalOperation | null;
  note: string; source: "user_manual"; realtime: false;
  broker_reconciled: false; full_account_verified: false;
  trade_execution_enabled: false;
};
export type ManualJournalResponse = {
  schema_version: "m8.manual_journal.v1"; source: "user_manual";
  notice: string; latest_revision: number; total_revisions: number;
  latest: ManualJournalRecord | null; history: ManualJournalRecord[];
  realtime: false; broker_reconciled: false; full_account_verified: false;
  trade_execution_enabled: false;
};

const notice = "仅为用户手工记录，未与券商核对；不代表实时账户、可卖数量或交易许可。";
const recordKeys = new Set([
  "id", "revision", "recorded_at", "observed_at", "available_cash", "total_equity",
  "lots", "operation", "note", "source", "realtime", "broker_reconciled",
  "full_account_verified", "trade_execution_enabled",
]);
const envelopeKeys = new Set([
  "schema_version", "source", "notice", "latest_revision", "total_revisions",
  "latest", "history", "realtime", "broker_reconciled", "full_account_verified",
  "trade_execution_enabled",
]);
const lotKeys = new Set(["symbol", "quantity", "paid_amount", "bought_at"]);
const operationKeys = new Set(["side", "symbol", "quantity", "price", "executed_at", "fee"]);

function exact(value: unknown, keys: Set<string>): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === keys.size && Object.keys(value).every((key) => keys.has(key));
}
function integer(value: unknown, minimum: number): value is number {
  return Number.isSafeInteger(value) && (value as number) >= minimum;
}
function amount(value: unknown, positive = false): value is string {
  return typeof value === "string" && /^(?:0|[1-9]\d{0,15})(?:\.\d{1,4})?$/.test(value) &&
    (!positive || Number(value) > 0);
}
function instant(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(20\d{2}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return false;
  const day = new Date(`${match[1]}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === match[1] &&
    Number.isFinite(Date.parse(value));
}
function symbol(value: unknown): value is string {
  return typeof value === "string" && /^[0-9A-Z.]{2,16}$/.test(value);
}
function safeFlags(value: Record<string, unknown>): boolean {
  return value.source === "user_manual" && value.realtime === false &&
    value.broker_reconciled === false && value.full_account_verified === false &&
    value.trade_execution_enabled === false;
}
function validRecord(value: unknown): value is ManualJournalRecord {
  if (!exact(value, recordKeys) || !safeFlags(value) ||
      typeof value.id !== "string" || !/^[0-9a-f-]{36}$/.test(value.id) ||
      !integer(value.revision, 1) || !instant(value.recorded_at) || !instant(value.observed_at) ||
      (value.available_cash !== null && !amount(value.available_cash)) ||
      (value.total_equity !== null && !amount(value.total_equity)) ||
      typeof value.note !== "string" || value.note.length > 200 ||
      !Array.isArray(value.lots) || value.lots.length > 100) return false;
  if (!value.lots.every((lot) => exact(lot, lotKeys) && symbol(lot.symbol) &&
      amount(lot.quantity, true) && (lot.paid_amount === null || amount(lot.paid_amount, true)) &&
      (lot.bought_at === null || (instant(lot.bought_at) &&
        Date.parse(lot.bought_at) <= Date.parse(value.observed_at as string))))) return false;
  const operation = value.operation;
  return operation === null || (exact(operation, operationKeys) &&
    (operation.side === "BUY" || operation.side === "SELL") && symbol(operation.symbol) &&
    amount(operation.quantity, true) && amount(operation.price, true) &&
    (operation.fee === null || amount(operation.fee)) && instant(operation.executed_at) &&
    Date.parse(operation.executed_at) <= Date.parse(value.observed_at as string));
}

export function canUseManualJournal(location: { protocol: string; hostname: string }): boolean {
  if (location.protocol === "https:") return true;
  return location.protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname.toLowerCase());
}

export function parseManualJournal(value: unknown): ManualJournalResponse {
  if (!exact(value, envelopeKeys) || value.schema_version !== "m8.manual_journal.v1" ||
      value.notice !== notice || !safeFlags(value) ||
      !integer(value.latest_revision, 0) || !integer(value.total_revisions, 0) ||
      value.total_revisions < value.latest_revision || !Array.isArray(value.history) ||
      value.history.length > 20 || !value.history.every(validRecord) ||
      !(value.latest === null || validRecord(value.latest))) {
    throw new Error("手工台账响应不可信。");
  }
  if ((value.latest_revision === 0) !== (value.latest === null) ||
      value.history.length !== Math.min(value.total_revisions as number, 20) ||
      (value.latest && (!value.history.length ||
        value.latest.id !== value.history[0].id ||
        value.latest.revision !== value.latest_revision)) ||
      value.history.some((row, index) => row.revision !== value.latest_revision as number - index)) {
    throw new Error("手工台账版本不一致。");
  }
  return value as ManualJournalResponse;
}
