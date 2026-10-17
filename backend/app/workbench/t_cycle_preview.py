"""Read-only, non-persistent preview of one manually entered T cycle."""
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.position import TCycle, TCycleStatus, TDirection


class TCyclePreviewRequest(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")
    direction: TDirection
    open_quantity: Decimal = Field(gt=0)
    open_price: Decimal = Field(gt=0)
    close_quantity: Decimal = Field(default=Decimal(0), ge=0)
    close_price: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_cycle(self) -> "TCyclePreviewRequest":
        if self.close_quantity > self.open_quantity:
            raise ValueError("闭环数量不得超过开仓数量")
        if (self.close_quantity > 0) != (self.close_price is not None):
            raise ValueError("闭环数量与闭环价格必须同时提供")
        return self


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
        "persisted": False,
        "broker_reconciled": False,
        "daily_cycle_limit_verified": False,
        "trade_execution_enabled": False,
        "notice": "仅本次手工输入的数学预览；未核验持仓、当日T次数或交易费用，不授权交易。",
    }
