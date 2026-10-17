/** Append-only, browser-local manual plans; no formal audit or server sync. */
export type PlanDraft = {
  id: string; version: number; savedAt: string; symbol: string;
  setup: string; entry: string; stop: string; target: string; notes: string;
};
export type PlanDraftInput = Pick<PlanDraft, "symbol" | "setup" | "entry" | "stop" | "target" | "notes">;
type Store = Pick<Storage, "getItem" | "setItem">;
export const DRAFT_KEY = "structure-swing.m8.manual-drafts.v1";
const MAX_VERSIONS = 200;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function validPrice(value: string): boolean {
  return value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0;
}
function validInput(input: PlanDraftInput): boolean {
  return /^[0-9]{6}$/.test(input.symbol) &&
    ["C", "A", "B", "NONE"].includes(input.setup) &&
    validPrice(input.entry) && validPrice(input.target) &&
    input.stop.trim() !== "" && Number.isFinite(Number(input.stop)) &&
    Number(input.stop) >= 0 && Number(input.stop) < Number(input.entry) &&
    input.notes.length <= 2000;
}

export function readDrafts(storage: Pick<Store, "getItem">): PlanDraft[] {
  const raw = storage.getItem(DRAFT_KEY);
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.length > MAX_VERSIONS) {
    throw new Error("本机草稿记录损坏；已停止写入，避免覆盖原数据。");
  }
  const seen = new Set<string>();
  const symbols = new Map<string, string>();
  for (const value of parsed) {
    if (!isRecord(value) || typeof value.id !== "string" ||
      !value.id.trim() || value.id.length > 128 ||
      typeof value.version !== "number" || !Number.isSafeInteger(value.version) ||
      value.version <= 0 ||
      typeof value.savedAt !== "string" ||
      !Number.isFinite(Date.parse(value.savedAt)) ||
      typeof value.symbol !== "string" || typeof value.setup !== "string" ||
      typeof value.entry !== "string" || typeof value.stop !== "string" ||
      typeof value.target !== "string" || typeof value.notes !== "string" ||
      !validInput({ symbol: value.symbol, setup: value.setup, entry: value.entry, stop: value.stop, target: value.target, notes: value.notes })) {
      throw new Error("本机草稿记录损坏；已停止写入，避免覆盖原数据。");
    }
    const id = value.id;
    const symbol = value.symbol as string;
    const key = id + ":" + value.version;
    if (seen.has(key) || (symbols.has(id) && symbols.get(id) !== symbol)) {
      throw new Error("计划版本重复或同一计划关联不同证券；已停止写入。");
    }
    seen.add(key);
    symbols.set(id, symbol);
  }
  return parsed as PlanDraft[];
}

export function saveDraft(
  storage: Store,
  input: PlanDraftInput,
  editingId: string | null,
  makeId: () => string = () => crypto.randomUUID(),
  now: () => string = () => new Date().toISOString(),
): { id: string; drafts: PlanDraft[] } {
  if (!validInput(input)) throw new Error("请核对证券代码、价格和结构失效价。");
  // Re-read on every save: never build a new version from stale React state.
  const current = readDrafts(storage);
  if (current.length >= MAX_VERSIONS) throw new Error("已达200个版本上限，请先备份。");
  const id = editingId ?? makeId();
  if (!id.trim() || id.length > 128) throw new Error("计划标识无效。");
  const versions = current.filter((item) => item.id === id);
  if (editingId && !versions.length) throw new Error("原计划版本不存在，已停止写入。");
  if (versions.some((item) => item.symbol !== input.symbol)) {
    throw new Error("同一计划不可更换证券代码，请新建独立计划。");
  }
  if (!editingId && versions.length) throw new Error("新计划标识重复，已停止写入。");
  const version = versions.reduce((max, item) => Math.max(max, item.version), 0) + 1;
  const savedAt = now();
  if (!Number.isFinite(Date.parse(savedAt))) throw new Error("保存时间无效。");
  const next: PlanDraft[] = [{ ...input, id, version, savedAt }, ...current];
  storage.setItem(DRAFT_KEY, JSON.stringify(next));
  return { id, drafts: next };
}
