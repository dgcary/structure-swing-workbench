import assert from "node:assert/strict";
import { test } from "node:test";
import { REVIEW_KEY, readReviews, saveReview } from "../src/reviewStore.ts";
import { saveDraft } from "../src/planDraftStore.ts";

function memoryStore() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}
const plan = { id: "plan-1", version: 2, symbol: "600000" };
const draft = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "" };
function seedPlan(store) {
  saveDraft(store, draft, null, () => "plan-1");
  saveDraft(store, draft, "plan-1");
}

test("manual reviews append to the latest browser history", () => {
  const store = memoryStore();
  seedPlan(store);
  saveReview(store, plan, "观察1", "结论1", () => "review-1");
  saveReview(store, plan, "观察2", "结论2", () => "review-2");
  assert.deepEqual(readReviews(store).map((r) => r.id), ["review-2", "review-1"]);
  assert.equal(readReviews(store)[1].observation, "观察1");
});

test("corrupted, empty and duplicated review history fail closed", () => {
  const store = memoryStore();
  seedPlan(store);
  const original = saveReview(store, plan, "观察", "结论", () => "review-1")[0];
  for (const raw of [
    "", "{}", JSON.stringify([original, original]),
    JSON.stringify([{ ...original, savedAt: "not-a-date" }]),
    JSON.stringify([{ ...original, lesson: "" }]),
  ]) {
    store.setItem(REVIEW_KEY, raw);
    assert.throws(() => saveReview(store, plan, "新观察", "新结论", () => "review-2"));
    assert.equal(store.getItem(REVIEW_KEY), raw);
  }
});

test("duplicate ids and invalid input do not overwrite review records", () => {
  const store = memoryStore();
  seedPlan(store);
  saveReview(store, plan, "观察", "结论", () => "review-1");
  const before = store.getItem(REVIEW_KEY);
  assert.throws(() => saveReview(store, plan, "观察", "结论", () => "review-1"));
  assert.throws(() => saveReview(store, plan, " ", "结论"));
  assert.throws(() => saveReview(store, { ...plan, version: 0 }, "观察", "结论"));
  assert.equal(store.getItem(REVIEW_KEY), before);
});

test("review ids do not require secure-context crypto.randomUUID", () => {
  const store = memoryStore();
  seedPlan(store);
  const items = saveReview(store, plan, "观察", "结论");
  assert.ok(items[0].id.length > 0);
  assert.equal(readReviews(store).length, 1);
});

test("orphan, wrong-version and cross-symbol manual reviews cannot be saved", () => {
  const store = memoryStore();
  assert.throws(() => saveReview(store, plan, "观察", "结论"), /版本不存在/);
  seedPlan(store);
  for (const invalid of [
    { ...plan, version: 3 },
    { ...plan, id: "unknown" },
    { ...plan, symbol: "000001" },
  ]) {
    assert.throws(() => saveReview(store, invalid, "观察", "结论"), /版本不存在|证券不匹配/);
    assert.equal(store.getItem(REVIEW_KEY), null);
  }
});
