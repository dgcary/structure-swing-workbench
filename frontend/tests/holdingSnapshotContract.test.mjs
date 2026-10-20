import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

test("rejects absent overview provenance", () => {
  assert.throws(() => assertReadOnlyOverview(null, "read_only"), /协议异常/);
  assert.throws(() => assertReadOnlyOverview({}, "read_only"), /协议异常/);
});
