import assert from "node:assert/strict";
import { test } from "node:test";
import { csvPreviewVerdict } from "../src/csvPreviewVerdict.ts";

const baseline = {
  row_count: 2,
  new_facts_in_isolated_preview: 2,
  duplicates_in_isolated_preview: 0,
  conflicts_in_isolated_preview: 0,
  valid_csv_structure: true,
};

test("clean preview remains explicitly non-persistent", () => {
  const verdict = csvPreviewVerdict(baseline);
  assert.equal(verdict.level, "ok");
  assert.match(verdict.heading, /未保存或导入/);
  assert.match(verdict.explanation, /尚未核对真实账户/);
});

test("conflicts take priority over duplicates and fail the preview", () => {
  const verdict = csvPreviewVerdict({
    ...baseline, duplicates_in_isolated_preview: 1,
    conflicts_in_isolated_preview: 1,
  });
  assert.equal(verdict.level, "error");
  assert.match(verdict.heading, /冲突.*未通过/);
  assert.match(verdict.explanation, /不能据此更新持仓/);
});

test("duplicate facts are a warning, not a clean success", () => {
  const verdict = csvPreviewVerdict({ ...baseline, duplicates_in_isolated_preview: 1 });
  assert.equal(verdict.level, "warning");
  assert.match(verdict.heading, /重复记录/);
});

test("invalid counts and structure fail closed", () => {
  for (const invalid of [
    { ...baseline, valid_csv_structure: false },
    { ...baseline, row_count: 0 },
    { ...baseline, conflicts_in_isolated_preview: -1 },
    { ...baseline, duplicates_in_isolated_preview: Number.NaN },
    { ...baseline, new_facts_in_isolated_preview: 0.5 },
  ]) {
    assert.throws(() => csvPreviewVerdict(invalid), /统计无效|结果缺失/);
  }
});
