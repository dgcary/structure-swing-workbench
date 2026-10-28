"""Read-only, non-persistent preview of one manually entered T cycle."""
from decimal import Decimal, localcontext

from pydantic import BaseModel, Field, model_validator

from app.position import TCycle, TCycleStatus, TDirection


# Match M1 persisted NUMERIC(20,4) quantity/money and NUMERIC(18,4)
# price boundaries. Without precision bounds, finite values such as 1e999999
# pass Decimal validation but can overflow the arithmetic context (HTTP 500).
# These are input-integrity limits, not additional trading strategy rules.
class ReverseTRiskInputs(BaseModel):
    """Explicit user assumptions, never independently verified account facts."""

    account_equity: Decimal = Field(gt=0, allow_inf_nan=False, max_digits=20, decimal_places=4)
    core_quantity: Decimal = Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=4)
    core_cost_price: Decimal = Field(gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4)
    main_invalidation_price: Decimal = Field(
        gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4
    )
    t_stop_price: Decimal = Field(gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4)
    existing_t_max_loss: Decimal = Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=4)
    other_positions_max_loss: Decimal = Field(
        ge=0, allow_inf_nan=False, max_digits=20, decimal_places=4
    )


class TCyclePreviewRequest(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")
    direction: TDirection
    open_quantity: Decimal = Field(gt=0, allow_inf_nan=False, max_digits=20, decimal_places=4)
    open_price: Decimal = Field(gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4)
    close_quantity: Decimal = Field(
        default=Decimal(0), ge=0, allow_inf_nan=False, max_digits=20, decimal_places=4
    )
    close_price: Decimal | None = Field(
        default=None, gt=0, allow_inf_nan=False, max_digits=18, decimal_places=4
    )
    risk_inputs: ReverseTRiskInputs | None = None

    @model_validator(mode="after")
    def validate_cycle(self) -> "TCyclePreviewRequest":
        if self.close_quantity > self.open_quantity:
            raise ValueError("闭环数量不得超过开仓数量")
        if (self.close_quantity > 0) != (self.close_price is not None):
            raise ValueError("闭环数量与闭环价格必须同时提供")
        if self.risk_inputs is not None:
            if self.direction is not TDirection.REVERSE:
                raise ValueError("独立T仓止损风险预览仅适用于反T先买")
            if self.risk_inputs.t_stop_price >= self.open_price:
                raise ValueError("反T独立止损价必须低于本次买入价")
        return self


def _preview_reverse_t_risk(data: TCyclePreviewRequest) -> dict[str, object] | None:
    inputs = data.risk_inputs
    if inputs is None:
        return None
    # Core and T inventory of this security use independent stops.
    # Other securities are included in the account-wide display only (§15.63).
    core_loss = max(
        Decimal(0),
        (inputs.core_cost_price - inputs.main_invalidation_price) * inputs.core_quantity,
    )
    new_t_loss = (data.open_price - inputs.t_stop_price) * data.open_quantity
    plan_loss = core_loss + new_t_loss + inputs.existing_t_max_loss
    account_total_loss = plan_loss + inputs.other_positions_max_loss
    plan_percent = plan_loss * Decimal(100) / inputs.account_equity
    account_total_percent = account_total_loss * Decimal(100) / inputs.account_equity
    # The 2%/3% audit tiers apply to one plan/action, never the cross-stock sum.
    level = "PASS" if plan_percent <= 2 else "WARNING" if plan_percent <= 3 else "HARD_FAIL"
    return {
        "projected_max_loss": str(plan_loss),
        "projected_account_risk_pct": str(plan_percent),
        "account_total_max_loss": str(account_total_loss),
        "account_total_risk_pct": str(account_total_percent),
        "other_positions_max_loss": str(inputs.other_positions_max_loss),
        "existing_t_max_loss": str(inputs.existing_t_max_loss),
        "core_max_loss": str(core_loss),
        "new_t_max_loss": str(new_t_loss),
        "level": level,
        "verified": False,
        "source": "用户手工假设",
        "warning": (
            "本票风险按核心仓、同票既有T仓及本次反T买入峰值计算；"
            "其他股票风险仅计入跨票合计展示，不参与本票2%/3%分级。"
            "未核验真实账户、昨日可卖数量、全部成交及仓位分配，不构成审计或交易许可。"
        ),
    }


def preview_t_cycle(data: TCyclePreviewRequest) -> dict[str, object]:
    # A NUMERIC(20,4) quantity multiplied by NUMERIC(18,4) price can
    # exceed Decimal's default 28-digit precision. Preserve exact cents
    # and threshold comparisons across the entire read-only preview.
    with localcontext() as context:
        context.prec = 64
        cycle = TCycle(data.direction, data.open_quantity, data.open_price)
        if data.close_quantity > 0:
            cycle.match(data.close_quantity, data.close_price)
        closed = cycle.status is TCycleStatus.CLOSED
        return {
            "schema_version": "m8.t_cycle_preview.v1",
            "symbol": data.symbol,
            "direction": data.direction.value,
            "cycle_status": cycle.status.value,
            "remaining_quantity": str(cycle.remaining_quantity),
            "realized_gross_pnl": str(cycle.matched_gross_pnl) if closed else None,
            "pending_matched_gross_pnl": str(cycle.matched_gross_pnl) if not closed else None,
            "projected_risk": _preview_reverse_t_risk(data),
            "persisted": False,
            "broker_reconciled": False,
            "daily_cycle_limit_verified": False,
            "trade_execution_enabled": False,
            "notice": "仅本次手工输入的数学预览；未核验持仓、当日T次数或交易费用，不授权交易。",
        }
