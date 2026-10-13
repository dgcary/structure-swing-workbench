"""Apply a validated CSV row to a staged account ledger."""

from app.account.imports import parse_number, parse_time
from app.account.ledger import AccountLedger
from app.account.models import Fact, Fill, FillSide, SourceKind
from app.account.recording import apply_fill


def apply_row(
    ledger: AccountLedger, kind: str, row: dict[str, str], source_id: str
) -> tuple[int, int, str | None]:
    if kind == "fills":
        side = row["side"].upper()
        if side not in FillSide.__members__:
            raise ValueError("成交方向只能是 BUY 或 SELL")
        item = Fill(
            row["fill_id"], row["symbol"], FillSide(side),
            parse_number(row["quantity"], "成交数量", positive=True),
            parse_number(row["price"], "成交价格", positive=True),
            parse_time(row["executed_at"]), source_id,
        )
        changed = apply_fill(ledger, item)
        return int(changed), int(not changed), item.symbol
    if kind == "holdings":
        symbol = row["symbol"]
        at = parse_time(row["as_of"])
        pairs = (
            (f"position:{symbol}:quantity", parse_number(row["quantity"], "持仓数量")),
            (f"position:{symbol}:cost", parse_number(row["cost"], "持仓成本")),
        )
    else:
        symbol = None
        at = parse_time(row["as_of"])
        pairs = (
            ("account.equity", parse_number(row["equity"], "账户权益")),
            ("account.available_cash", parse_number(row["available_cash"], "可用资金")),
        )
    imported = 0
    for key, value in pairs:
        imported += int(
            ledger.record_fact(Fact(key, value, SourceKind.SNAPSHOT, source_id, at))
        )
    return imported, len(pairs) - imported, symbol
