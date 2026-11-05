"""Read-only workbench overview; missing values are not zero."""

from app.account.ledger import AccountLedger
from app.workbench.holdings import project_holdings

FIELDS = {
    "equity": ("账户总权益", "account.equity", "元"),
    "available_cash": ("可用资金", "account.available_cash", "元"),
    "position_ratio": ("当前总仓位", None, "%"),
    "position_count": ("持仓股票数", None, "只"),
    "account_risk": ("当前账户总风险", None, "%"),
    "t_cycles_today": ("当日T次数", None, "次"),
    "open_t_cycles": ("未完成T循环", None, "个"),
    "rotation_status": ("日内换仓状态", None, ""),
    "highest_audit": ("当前最高审计等级", None, ""),
}


def build_overview(
    ledger: AccountLedger | None = None, *, persisted: dict[str, object] | None = None
) -> dict[str, object]:
    """Only publish metrics that carry both an explicit source and a dated observation."""
    metrics = []
    persisted_metrics = persisted.get("metrics", {}) if persisted is not None else {}
    for key, (label, ledger_key, unit) in FIELDS.items():
        fact = ledger.facts.get(ledger_key) if ledger and ledger_key else None
        sourced = persisted_metrics.get(key) if isinstance(persisted_metrics, dict) else None
        value = str(fact.value) if fact else sourced.get("value") if sourced else None
        source = (
            f"{fact.source.value}/{fact.source_id}" if fact else
            sourced.get("source") if sourced else None
        )
        at = (
            fact.observed_at.isoformat() if fact else
            sourced.get("as_of") if sourced else None
        )
        available = value is not None and bool(source) and bool(at)
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "value": value if available else None,
            "status": "available" if available else "unavailable",
            "source": source if available else None,
            "as_of": at if available else None,
            "availability_reason": None if available else "缺少可追溯的数据来源",
        })
    return {
        "schema_version": "m8.overview.v1",
        "mode": "read_only",
        "notice": "未接入的数据不是零、空仓或审计通过；不得据此交易。",
        "metrics": metrics,
        "holdings": project_holdings(ledger) if ledger is not None else (
            persisted.get("holdings") if persisted is not None else None
        ),
        "effective_plans": persisted.get("effective_plans") if persisted is not None else None,
        "attribution_pending_plans": persisted.get("attribution_pending_plans") if persisted is not None else None,
        "pending_actions": persisted.get("pending_actions") if persisted is not None else None,
        "audit_results": persisted.get("audit_results") if persisted is not None else None,
        "t_cycle_evidence": persisted.get("t_cycle_evidence") if persisted is not None else None,
        "trade_execution_enabled": False,
    }
