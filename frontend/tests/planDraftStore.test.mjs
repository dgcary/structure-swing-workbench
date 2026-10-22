import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, readDrafts, saveDraft } from "../src/planDraftStore.ts";

function memoryStore() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}
const input = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "人工" };

test("new versions are appended to the latest browser history", () => {
  const store = memoryStore();
  const first = saveDraft(store, input, null, () => "plan-1");
  saveDraft(store, { ...input, notes: "修订" }, first.id);
  assert.deepEqual(readDrafts(store).map((item) => item.version), [2, 1]);
  assert.equal(readDrafts(store)[1].notes, "人工");
});

test("changing the stock of an existing plan fails without overwriting history", () => {
  const store = memoryStore();
  saveDraft(store, input, null, () => "plan-1");
  const before = store.getItem(DRAFT_KEY);
  assert.throws(() => saveDraft(store, { ...input, symbol: "000001" }, "plan-1"));
  assert.equal(store.getItem(DRAFT_KEY), before);
});

test("corrupt, duplicate or cross-symbol versions fail closed", () => {
  const store = memoryStore();
  const original = saveDraft(store, input, null, () => "plan-1").drafts[0];
  for (const records of [
    [original, original],
    [original, { ...original, version: 2, symbol: "000001" }],
    [{ ...original, entry: "NaN" }],
  ]) {
    store.setItem(DRAFT_KEY, JSON.stringify(records));
    const before = store.getItem(DRAFT_KEY);
    assert.throws(() => saveDraft(store, input, "plan-1"));
    assert.equal(store.getItem(DRAFT_KEY), before);
  }
});

test("invalid prices and missing editing ids never create a plan", () => {
  const store = memoryStore();
  assert.throws(() => saveDraft(store, input, "missing"));
  assert.throws(() => saveDraft(store, { ...input, entry: "0" }, null));
  assert.equal(store.getItem(DRAFT_KEY), null);
});

test("empty stored value is corruption, not permission to overwrite", () => {
  const store = memoryStore();
  store.setItem(DRAFT_KEY, "");
  assert.throws(() => saveDraft(store, input, null));
  assert.equal(store.getItem(DRAFT_KEY), "");
});

test("new plan ids work without secure-context crypto APIs", () => {
  const store = memoryStore();
  const saved = saveDraft(store, input, null);
  assert.equal(typeof saved.id, "string");
  assert.ok(saved.id.length > 0);
  assert.equal(readDrafts(store).length, 1);
});


test("decimal prices are accepted without normalizing the user's original text", () => {
  for (const [entry, stop, target] of [
    ["10.50", "9.25", "12.75"],
    [".5", "0", "1.25"],
    ["1e1", "9e0", "1.2e1"],
    ["1E+1", "9.00", "1.20E+1"],
    [" 10.25 ", " 9.50 ", " 12.00 "],
    ["0.0001", "0.00001", "0.0002"],
  ]) {
    const store = memoryStore();
    const data = { ...input, entry, stop, target };
    const result = saveDraft(store, data, null, () => "decimal");
    assert.equal(result.drafts.length, 1);
    assert.equal(result.drafts[0].entry, entry);
    assert.equal(result.drafts[0].stop, stop);
    assert.equal(result.drafts[0].target, target);
    assert.equal(readDrafts(store)[0].entry, entry);
  }
});

test("non-decimal, non-finite and overflow price lexemes fail closed on save", () => {
  const invalid = [
    "0x10", "0X10", "0b1010", "0B1010", "0o12", "0O12",
    "NaN", "Infinity", "+Infinity", "-Infinity", "1e309", "1E9999",
    "1e-9999", "0", "-1", "1.", "1_000", "10px", "",
  ];
  const store = memoryStore();
  saveDraft(store, input, null, () => "original");
  for (const price of invalid) {
    for (const field of ["entry", "target"]) {
      const before = store.getItem(DRAFT_KEY);
      assert.throws(() => saveDraft(store, { ...input, [field]: price }, "original"),
        undefined, `${field}=${JSON.stringify(price)}`);
      assert.equal(store.getItem(DRAFT_KEY), before);
    }
  }
  for (const stop of ["0x0", "0b0", "0o0", "NaN", "Infinity", "1e309", "-1", "10"]) {
    const before = store.getItem(DRAFT_KEY);
    assert.throws(() => saveDraft(store, { ...input, stop }, "original"),
      undefined, `stop=${JSON.stringify(stop)}`);
    assert.equal(store.getItem(DRAFT_KEY), before);
  }
});

test("legacy stored drafts with non-decimal prices cannot be read or overwritten", () => {
  const store = memoryStore();
  const original = saveDraft(store, input, null, () => "legacy").drafts[0];
  const invalid = ["0x10", "0b1010", "0o12", "NaN", "Infinity", "1e309", "1e-9999"];
  for (const price of invalid) {
    for (const field of ["entry", "stop", "target"]) {
      store.setItem(DRAFT_KEY, JSON.stringify([{ ...original, [field]: price }]));
      const before = store.getItem(DRAFT_KEY);
      assert.throws(() => readDrafts(store), undefined, `legacy ${field}=${price}`);
      assert.throws(() => saveDraft(store, input, "legacy"), undefined, `edit ${field}=${price}`);
      assert.throws(() => saveDraft(store, input, null, () => "new"), undefined,
        `new ${field}=${price}`);
      assert.equal(store.getItem(DRAFT_KEY), before);
    }
  }
});
