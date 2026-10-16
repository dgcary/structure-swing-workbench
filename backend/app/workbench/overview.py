"""Read-only workbench overview; missing values are not zero."""

from app.account.ledger import AccountLedger

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


def build_overview(ledger: AccountLedger | None = None) -> dict[str, object]:
    metrics = []
    for key, (label, ledger_key, unit) in FIELDS.items():
        fact = ledger.facts.get(ledger_key) if ledger and ledger_key else None
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "value": str(fact.value) if fact else None,
            "status": "available" if fact else "unavailable",
            "source": f"{fact.source.value}/{fact.source_id}" if fact else None,
            "as_of": fact.observed_at.isoformat() if fact else None,
            "availability_reason": None if fact else "缺少可追溯的数据来源",
        })
    return {
        "schema_version": "m8.overview.v1",
        "mode": "read_only",
        "notice": "未接入的数据不是零、空仓或审计通过；不得据此交易。",
        "metrics": metrics,
        "holdings": None,
        "effective_plans": None,
        "pending_actions": None,
        "audit_results": None,
        "trade_execution_enabled": False,
    }
