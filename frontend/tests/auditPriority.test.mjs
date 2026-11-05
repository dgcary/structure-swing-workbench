import assert from "node:assert/strict";
import { test } from "node:test";
import { orderHistoricalAudits } from "../src/auditPriority.ts";

test("historical audit exceptions put hard failures first without changing records", () => {
  const rows = [
    { id: "pass", level: "pass", as_of: "2026-10-29T12:00:00+08:00" },
    { id: "warning-old", level: "warning", as_of: "2026-10-27T12:00:00+08:00" },
    { id: "hard-old", level: "hard_fail", as_of: "2026-10-26T12:00:00+08:00" },
    { id: "soft", level: "overridable_fail", as_of: "2026-10-28T12:00:00+08:00" },
    { id: "warning-new", level: "warning", as_of: "2026-10-29T10:00:00+08:00" },
  ];
  const ordered = orderHistoricalAudits(rows);
  assert.deepEqual(ordered.map((row) => row.id), [
    "hard-old", "soft", "warning-new", "warning-old", "pass",
  ]);
  assert.deepEqual(rows.map((row) => row.id), [
    "pass", "warning-old", "hard-old", "soft", "warning-new",
  ]);
});

test("undated history stays behind dated records of the same severity", () => {
  const rows = [
    { id: "undated", level: "hard_fail", as_of: null },
    { id: "dated", level: "hard_fail", as_of: "2026-10-29T10:00:00+08:00" },
  ];
  assert.deepEqual(orderHistoricalAudits(rows).map((row) => row.id), ["dated", "undated"]);
});
