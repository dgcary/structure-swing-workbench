"""Read-only holdings projection from existing M5 facts."""

from app.account.ledger import AccountLedger
from app.account.models import ImportConflictError
from app.account.position_view import position_view


def project_holdings(ledger: AccountLedger | None) -> list[dict[str, object]] | None:
    if ledger is None:
        return None
    symbols = {
        key.split(":")[1] for key in ledger.facts
        if key.startswith("position:") and key.endswith(":quantity")
        and len(key.split(":")) == 3
    }
    symbols.update(fill.symbol for fill in ledger.fills.values())
    if not symbols:
        return None
    rows: list[dict[str, object]] = []
    for symbol in sorted(symbols):
        baseline = ledger.facts.get(f"position:{symbol}:quantity")
        # Without a dated holdings baseline, fills prove only a net change,
        # not an actual position. Keep their provenance visible separately.
        symbol_fills = [
            fill for fill in ledger.fills.values()
            if fill.symbol == symbol
            and (baseline is None or fill.executed_at > baseline.observed_at)
        ]
        latest_fill = max(symbol_fills, key=lambda fill: fill.executed_at, default=None)
        source = (
            " + ".join(filter(None, (
                f"{baseline.source.value}/{baseline.source_id}" if baseline else None,
                f"成交记录/{latest_fill.source_id}" if latest_fill else None,
            ))) or None
        )
        at = (
            latest_fill.executed_at.isoformat() if latest_fill else
            baseline.observed_at.isoformat() if baseline else None
        )
        try:
            view = position_view(ledger, symbol)
        except ImportConflictError:
            rows.append({
                "symbol": symbol, "status": "conflict", "quantity": None,
                "broker_display_cost": None, "source": source, "as_of": at,
                "core_quantity": None, "t_quantity": None,
                "applied_fill_ids": [], "unanchored_fill_delta": None,
                "warning": "成交与持仓快照冲突，请人工核对。",
            })
            continue
        state = (
            "unanchored" if view.quantity is None else
            "partial" if view.broker_display_cost is None else "snapshot"
        )
        rows.append({
            "symbol": symbol, "status": state,
            "quantity": str(view.quantity) if view.quantity is not None else None,
            "broker_display_cost": (
                str(view.broker_display_cost)
                if view.broker_display_cost is not None else None
            ),
            "source": source, "as_of": at,
            "applied_fill_ids": list(view.applied_fill_ids),
            "unanchored_fill_delta": (
                str(view.unanchored_fill_delta) if view.quantity is None else None
            ),
            "core_quantity": None, "t_quantity": None,
            "warning": (
                "缺少基准快照，不能推断真实持仓。" if view.quantity is None else
                "数量可追溯，但券商成本不可验证。" if view.broker_display_cost is None else
                "核心仓和T仓未核实，账户全量持仓未核实。"
            ),
        })
    return rows
