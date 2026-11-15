"""Pydantic request models for the workbench API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import (
    ActionType,
    EntryMode,
    OrderSide,
    PositionBucketType,
    SetupType,
    StructureStage,
    TargetType,
)


class PlanVersionData(BaseModel):
    """User-editable plan-version fields; values are explicit user input only."""

    setup_type: SetupType | None = None
    structure_stage: StructureStage | None = None
    structure_low_price: Decimal | None = None
    key_support_price: Decimal | None = None
    key_resistance_price: Decimal | None = None
    reversal_confirmed: bool | None = None
    structure_invalidated: bool | None = None
    structure_invalidation_price: Decimal | None = None
    structure_invalidation_condition: str | None = None
    entry_mode: EntryMode | None = None
    planned_total_position_amount: Decimal | None = None
    planned_total_position_pct: Decimal | None = None
    initial_entry_price_low: Decimal | None = None
    initial_entry_price_high: Decimal | None = None
    initial_entry_pct: Decimal | None = None
    confirmation_add_enabled: bool | None = None
    confirmation_trigger_price: Decimal | None = None
    confirmation_add_pct: Decimal | None = None
    t_reserve_pct: Decimal | None = None
    first_target_price: Decimal | None = None
    first_target_type: TargetType | None = None
    first_target_reduce_pct: Decimal | None = None
    remaining_exit_condition: str | None = None
    remaining_exit_condition_triggered: bool | None = None
    valid_until: date | None = None


class PlanCreateRequest(BaseModel):
    instrument_code: str = Field(min_length=1, max_length=16)
    instrument_name: str = Field(min_length=1, max_length=64)
    version: PlanVersionData
    user_note: str | None = None
    account_equity: Decimal | None = None


class PlanRevisionRequest(BaseModel):
    changes: PlanVersionData
    reason: str | None = None
    account_equity: Decimal | None = None


class PlanNoteRequest(BaseModel):
    user_note: str | None = None


class AuditRunRequest(BaseModel):
    """Optional explicit equity; otherwise the latest account snapshot is used."""

    account_equity: Decimal | None = None


class AuditDecisionRequest(BaseModel):
    approve: bool
    user_confirmed: bool = False
    override_reason: str | None = None


class ActionCreateRequest(BaseModel):
    action_type: ActionType
    side: OrderSide
    planned_price_low: Decimal | None = None
    planned_price_high: Decimal | None = None
    planned_quantity: Decimal | None = None
    planned_position_pct: Decimal | None = None
    t_cycle_key: str | None = None
    user_note: str | None = None


class FillCreateRequest(BaseModel):
    quantity: Decimal
    price: Decimal
    side: OrderSide | None = None
    fee: Decimal = Decimal(0)
    executed_at: datetime
    source: str = "manual"
    external_execution_id: str | None = None
    override_confirmed: bool = False
    override_reason: str | None = None


class BucketItem(BaseModel):
    bucket_type: PositionBucketType
    quantity: Decimal
    strategy_cost_price: Decimal | None = None
    effective_cost_price: Decimal | None = None
    realized_t_pnl: Decimal | None = None


class PositionItem(BaseModel):
    instrument_code: str = Field(min_length=1, max_length=16)
    instrument_name: str = Field(min_length=1, max_length=64)
    total_quantity: Decimal
    market_value: Decimal | None = None
    broker_cost_price: Decimal | None = None
    buckets: list[BucketItem] = Field(default_factory=list)


class AccountSnapshotRequest(BaseModel):
    captured_at: datetime
    total_equity: Decimal
    available_cash: Decimal
    source: str = "manual"
    source_note: str | None = None
    positions: list[PositionItem] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    source: str
    reference: str
    observed_at: str


class CandidateFactItem(BaseModel):
    value: str
    evidence: EvidenceItem


class CandidateRiskItem(BaseModel):
    code: str
    state: str
    evidence: EvidenceItem


class CandidateScreenRequest(BaseModel):
    symbol: str
    name: str
    board: CandidateFactItem
    liquidity: CandidateFactItem
    size: CandidateFactItem
    listing_age: CandidateFactItem
    risks: list[CandidateRiskItem] = Field(default_factory=list)
    review_lane: str | None = None
    review_lane_evidence: EvidenceItem | None = None


def version_payload(data: PlanVersionData) -> dict[str, Any]:
    """Convert request fields into service-compatible values, dropping unset fields."""

    return {key: value for key, value in data.model_dump().items() if value is not None}
