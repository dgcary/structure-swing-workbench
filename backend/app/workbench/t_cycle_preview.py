"""Read-only, non-persistent preview of one manually entered T cycle."""
from decimal import Decimal

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
    # Core and new reverse-T inventory use independent stops. Both existing
    # T inventory and other positions must be explicitly accounted for.
    core_loss = max(
        Decimal(0),
        (inputs.core_cost_price - inputs.main_invalidation_price) * inputs.core_quantity,
    )
    new_t_loss = (data.open_price - inputs.t_stop_price) * data.open_quantity
    projected_loss = (
        core_loss + new_t_loss + inputs.existing_t_max_loss
        + inputs.other_positions_max_loss
    )
    percent = projected_loss * Decimal(100) / inputs.account_equity
    level = "PASS" if percent <= 2 else "WARNING" if percent <= 3 else "HARD_FAIL"
    return {
        "projected_max_loss": str(projected_loss),
        "projected_account_risk_pct": str(percent),
        "core_max_loss": str(core_loss),
        "new_t_max_loss": str(new_t_loss),
        "level": level,
        "verified": False,
        "source": "用户手工假设",
        "warning": (
            "仅按输入的核心仓、既有T仓及其他持仓风险计算反T买入后的最大暴露；"
            "未核验真实账户、昨日可卖数量、全部成交及仓位分配，不构成审计或交易许可。"
        ),
    }


def preview_t_cycle(data: TCyclePreviewRequest) -> dict[str, object]:
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
