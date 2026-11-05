type Lot = { symbol: string; quantity: string };

function scaledQuantity(value: string): bigint {
  const matched = /^(0|[1-9][0-9]*)(?:\.([0-9]{1,4}))?$/.exec(value.trim());
  if (!matched) throw new Error("数量须为最多四位小数的正数。");
  const scaled = BigInt(matched[1]) * 10_000n + BigInt((matched[2] ?? "").padEnd(4, "0"));
  if (scaled <= 0n) throw new Error("数量须大于零。");
  return scaled;
}

export function buildSellAllocations(
  lots: Lot[], symbol: string, total: string, entries: Record<number, string>,
): { lot_index: number; quantity: string }[] {
  const matching = lots.map((lot, index) => ({ lot, index }))
    .filter(({ lot }) => lot.symbol === symbol.trim().toUpperCase());
  if (!matching.length) throw new Error("当前版本找不到这只证券的持仓批次。");
  const requested = scaledQuantity(total);
  const allocations = matching.flatMap(({ lot, index }) => {
    const entry = entries[index]?.trim() || (matching.length === 1 ? total.trim() : "");
    if (!entry) return [];
    const amount = scaledQuantity(entry);
    if (amount > scaledQuantity(lot.quantity)) throw new Error("卖出超过所选批次的持有数量。");
    return [{ lot_index: index, quantity: entry }];
  });
  const allocated = allocations.reduce((sum, entry) => sum + scaledQuantity(entry.quantity), 0n);
  if (allocated !== requested) throw new Error("各批扣减数量之和必须等于本次卖出总数。");
  return allocations;
}
