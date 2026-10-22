"""Non-persistent preview of user-entered plan discipline fields."""

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.audit.engine import (
    aggregate,
    audit_position_split,
    audit_single_trade_risk,
    audit_structure_invalidation,
)
from app.domain.enums import ActionType


class PlanPreviewRequest(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")
    account_equity: Decimal = Field(gt=0)
    planned_quantity: Decimal = Field(gt=0)
    planned_entry_price: Decimal = Field(gt=0)
    invalidation_price: Decimal = Field(ge=0)
    initial_pct: Decimal = Field(ge=0, le=100)
    confirmation_pct: Decimal = Field(ge=0, le=100)
    t_reserve_pct: Decimal = Field(ge=0, le=100)
    action_type: ActionType
    structure_invalidated: bool

    @model_validator(mode="after")
    def validate_plan(self) -> "PlanPreviewRequest":
        if self.invalidation_price >= self.planned_entry_price:
            raise ValueError("结构失效价必须低于计划入场价")
        if self.initial_pct + self.confirmation_pct + self.t_reserve_pct != 100:
            raise ValueError("仓位比例合计必须为100%")
        return self


def preview_plan(data: PlanPreviewRequest) -> dict[str, object]:
    max_loss = (data.planned_entry_price - data.invalidation_price) * data.planned_quantity
    risk_pct = max_loss / data.account_equity * Decimal(100)
    findings = [
        audit_single_trade_risk(risk_pct),
        *audit_position_split(
            initial_pct=data.initial_pct,
            confirmation_pct=data.confirmation_pct,
            t_reserve_pct=data.t_reserve_pct,
        ),
        audit_structure_invalidation(
            invalidated=data.structure_invalidated,
            action_type=data.action_type,
        ),
    ]
    report = aggregate(findings)
    priority = {"hard_fail": 3, "overridable_fail": 2, "warning": 1, "pass": 0}
    return {
        "schema_version": "m8.plan_preview.v1",
        "symbol": data.symbol,
        "mode": "partial_preview",
        "input_source": "user",
        "persisted": False,
        "formal_audit_completed": False,
        "executable": False,
        "trade_execution_enabled": False,
        "notice": "仅预审已输入字段，尚未完成完整计划与动作审计；不授权交易。",
        "planned_max_loss": str(max_loss),
        "account_risk_pct": str(risk_pct),
        "highest_checked_level": report.level.value,
        "highest_checked_level_zh": report.level.label_zh,
        "findings": [
            {
                "rule": finding.rule,
                "level": finding.level.value,
                "level_zh": finding.level.label_zh,
                "message": finding.message,
            }
            for finding in sorted(
                findings, key=lambda item: priority[item.level.value], reverse=True
            )
        ],
    }
