import { DRAFT_KEY, readDrafts } from "./planDraftStore.ts";

/** Browser-only manual reviews; never a verified fill, P&L or formal audit. */
export type ManualReview = {
  id: string; planId: string; version: number; symbol: string;
  savedAt: string; observation: string; lesson: string;
};
export type ReviewPlan = { id: string; version: number; symbol: string };
type Store = Pick<Storage, "getItem" | "setItem">;
export const REVIEW_KEY = "structure-swing.m8.manual-reviews.v1";
const MAX_REVIEWS = 200;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function validText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= 2000;
}
function validReview(value: unknown): value is ManualReview {
  return isRecord(value) && typeof value.id === "string" &&
    value.id.trim().length > 0 && value.id.length <= 128 &&
    typeof value.planId === "string" && value.planId.trim().length > 0 &&
    value.planId.length <= 128 &&
    typeof value.version === "number" && Number.isSafeInteger(value.version) &&
    value.version > 0 && typeof value.symbol === "string" &&
    /^[0-9]{6}$/.test(value.symbol) &&
    typeof value.savedAt === "string" &&
    Number.isFinite(Date.parse(value.savedAt)) &&
    validText(value.observation) && validText(value.lesson);
}

export function readReviews(storage: Pick<Store, "getItem">): ManualReview[] {
  const raw = storage.getItem(REVIEW_KEY);
  if (raw === null) return [];
  // An empty string is corruption, not a blank history to silently overwrite.
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.length > MAX_REVIEWS) {
    throw new Error("本机复盘记录损坏；已停止写入。");
  }
  const seen = new Set<string>();
  for (const item of parsed) {
    if (!validReview(item) || seen.has(item.id)) {
      throw new Error("本机复盘记录损坏或编号重复；已停止写入。");
    }
    seen.add(item.id);
  }
  return parsed as ManualReview[];
}

export function saveReview(
  storage: Store,
  plan: ReviewPlan,
  observation: string,
  lesson: string,
  makeId: () => string = () => Date.now().toString(36) + Math.random().toString(36).slice(2),
  now: () => string = () => new Date().toISOString(),
): ManualReview[] {
  if (!plan.id.trim() || plan.id.length > 128 ||
      !Number.isSafeInteger(plan.version) || plan.version <= 0 ||
      !/^[0-9]{6}$/.test(plan.symbol) ||
      !validText(observation) || !validText(lesson)) {
    throw new Error("请选择有效计划版本并填写不超过2000字的复盘内容。");
  }
  // Always re-read the latest history; never overwrite changes from another tab.
  const draftSnapshot = storage.getItem(DRAFT_KEY);
  const reviewSnapshot = storage.getItem(REVIEW_KEY);
  const drafts = readDrafts({ getItem: () => draftSnapshot });
  if (!drafts.some((item) =>
    item.id === plan.id && item.version === plan.version &&
    item.symbol === plan.symbol)) {
    throw new Error("关联的人工计划版本不存在或证券不匹配；未保存复盘。");
  }
  const current = readReviews({ getItem: () => reviewSnapshot });
  if (current.length >= MAX_REVIEWS) throw new Error("复盘已达200条上限，请先备份。");
  const id = makeId(), savedAt = now();
  if (!id.trim() || id.length > 128 || current.some((item) => item.id === id) ||
      !Number.isFinite(Date.parse(savedAt))) {
    throw new Error("复盘编号重复或保存时间无效，未覆盖原记录。");
  }
  const next = [{
    id, planId: plan.id, version: plan.version, symbol: plan.symbol,
    savedAt, observation: observation.trim(), lesson: lesson.trim(),
  }, ...current];
  if (storage.getItem(DRAFT_KEY) !== draftSnapshot ||
      storage.getItem(REVIEW_KEY) !== reviewSnapshot) {
    throw new Error("保存期间计划或复盘记录已被其他页面更新，请刷新后重试。");
  }
  storage.setItem(REVIEW_KEY, JSON.stringify(next));
  return next;
}
