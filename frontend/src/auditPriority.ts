/** Show the most severe historical finding first, then the newest within a level. */
const priority: Record<string, number> = {
  hard_fail: 0,
  overridable_fail: 1,
  warning: 2,
  pass: 3,
};

export function orderHistoricalAudits<T extends { level: string; as_of: string | null }>(
  rows: readonly T[],
): T[] {
  return [...rows].sort((a, b) => {
    const severity = (priority[a.level] ?? 4) - (priority[b.level] ?? 4);
    if (severity !== 0) return severity;
    return (b.as_of === null ? -Infinity : Date.parse(b.as_of)) -
      (a.as_of === null ? -Infinity : Date.parse(a.as_of));
  });
}
