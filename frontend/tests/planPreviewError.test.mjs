import assert from "node:assert/strict";
import { test } from "node:test";
import { planPreviewError } from "../src/planPreviewError.ts";

test("field-specific validation errors are explained in Chinese", () => {
  const message = planPreviewError(422, { detail: [
    { loc: ["body", "symbol"], type: "string_pattern_mismatch", msg: "String should match pattern" },
    { loc: ["body", "account_equity"], type: "greater_than", msg: "Input should be greater than 0" },
    { loc: ["body", "action_type"], type: "enum", msg: "Invalid enum" },
  ] });
  assert.match(message, /证券代码：格式不正确/);
  assert.match(message, /账户权益：必须大于零/);
  assert.match(message, /用户计划动作：不是允许的操作类型/);
});

test("business validation reasons are retained without claiming an audit passed", () => {
  const message = planPreviewError(422, { detail: [
    { loc: ["body"], type: "value_error", msg: "Value error, 仓位比例合计必须为100%" },
  ] });
  assert.match(message, /仓位比例合计必须为100%/);
  assert.match(message, /校验失败/);
});

test("untrusted server errors are not shown verbatim", () => {
  assert.match(planPreviewError(503, { detail: "internal password=secret" }), /预审接口失败/);
  assert.doesNotMatch(planPreviewError(503, { detail: "internal password=secret" }), /secret/);
  assert.match(planPreviewError(422, { detail: [{ loc: ["body"], type: "missing" }] }), /不能为空/);
});
