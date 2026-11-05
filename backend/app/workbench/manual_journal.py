"""Versioned user-entered account notes, isolated from broker and formal facts."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ManualJournalRevision


class ManualJournalConflict(ValueError):
    """The client based a change on an older journal revision."""


def _money(value: Decimal | None, *, positive: bool = False, price: bool = False) -> Decimal | None:
    if value is None:
        return None
    upper = Decimal("1e14") if price else Decimal("1e16")
    if (not value.is_finite() or value < 0 or (positive and value == 0)
            or value >= upper or value.normalize().as_tuple().exponent < -4):
        raise ValueError("金额、价格或数量必须为有效的四位小数内数值")
    return Decimal(0) if value == 0 else value


def _time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    if value.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("时间不能晚于当前时间")
    return value


class ManualLot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=2, max_length=16)
    quantity: Decimal
    paid_amount: Decimal | None = None
    bought_at: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9A-Z.]{2,16}", value):
            raise ValueError("证券代码格式无效")
        return value

    @field_validator("quantity")
    @classmethod
    def valid_amount(cls, value: Decimal) -> Decimal:
        return _money(value, positive=True)  # type: ignore[return-value]

    @field_validator("paid_amount")
    @classmethod
    def valid_paid_amount(cls, value: Decimal | None) -> Decimal | None:
        return _money(value, positive=True)

    @field_validator("bought_at")
    @classmethod
    def valid_time(cls, value: datetime | None) -> datetime | None:
        return _time(value) if value is not None else None


class ManualOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["BUY", "SELL"]
    symbol: str = Field(min_length=2, max_length=16)
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    fee: Decimal | None = None

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        return ManualLot.valid_symbol(value)

    @field_validator("quantity")
    @classmethod
    def valid_quantity(cls, value: Decimal) -> Decimal:
        return _money(value, positive=True)  # type: ignore[return-value]

    @field_validator("price")
    @classmethod
    def valid_price(cls, value: Decimal) -> Decimal:
        return _money(value, positive=True, price=True)  # type: ignore[return-value]

    @field_validator("fee")
    @classmethod
    def valid_fee(cls, value: Decimal | None) -> Decimal | None:
        return _money(value)

    @field_validator("executed_at")
    @classmethod
    def valid_time(cls, value: datetime) -> datetime:
        return _time(value)


class ManualJournalWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    observed_at: datetime
    available_cash: Decimal | None = None
    total_equity: Decimal | None = None
    lots: list[ManualLot] = Field(max_length=100)
    operation: ManualOperation | None = None
    note: str = Field(default="", max_length=200)

    @field_validator("observed_at")
    @classmethod
    def valid_observed_at(cls, value: datetime) -> datetime:
        return _time(value)

    @field_validator("available_cash", "total_equity")
    @classmethod
    def valid_money(cls, value: Decimal | None) -> Decimal | None:
        return _money(value)

    @model_validator(mode="after")
    def chronological(self) -> "ManualJournalWrite":
        if any(lot.bought_at is not None and lot.bought_at > self.observed_at
               for lot in self.lots):
            raise ValueError("买入时间不得晚于账户观察时间")
        if self.operation and self.operation.executed_at > self.observed_at:
            raise ValueError("操作时间不得晚于账户观察时间")
        return self


class ManualOperationApply(BaseModel):
    """Apply one explicitly entered trade to the current self-reported lots."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    observed_at: datetime
    operation: ManualOperation
    sell_lot_index: int | None = Field(default=None, ge=0)
    sell_allocations: list["ManualSellAllocation"] | None = Field(default=None, max_length=100)
    available_cash: Decimal | None = None
    total_equity: Decimal | None = None
    note: str = Field(default="", max_length=200)

    @field_validator("observed_at")
    @classmethod
    def valid_observed_at(cls, value: datetime) -> datetime:
        return _time(value)

    @field_validator("available_cash", "total_equity")
    @classmethod
    def valid_money(cls, value: Decimal | None) -> Decimal | None:
        return _money(value)


class ManualSellAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lot_index: int = Field(ge=0)
    quantity: Decimal

    @field_validator("quantity")
    @classmethod
    def valid_quantity(cls, value: Decimal) -> Decimal:
        return _money(value, positive=True)  # type: ignore[return-value]


def _record_view(row: ManualJournalRevision) -> dict[str, object]:
    return {
        "id": row.id,
        "revision": row.revision,
        "recorded_at": row.recorded_at,
        "observed_at": row.observed_at,
        "available_cash": _decimal_text(row.available_cash) if row.available_cash is not None else None,
        "total_equity": _decimal_text(row.total_equity) if row.total_equity is not None else None,
        "lots": row.lots,
        "operation": row.operation,
        "note": row.note,
        "source": "user_manual",
        "realtime": False,
        "broker_reconciled": False,
        "full_account_verified": False,
        "trade_execution_enabled": False,
    }


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def append_manual_record(session: Session, payload: ManualJournalWrite) -> dict[str, object]:
    """Append one whole self-report; unique revision prevents silent concurrent overwrites."""
    latest_row = session.scalar(select(ManualJournalRevision).order_by(
        ManualJournalRevision.revision.desc()
    ).limit(1))
    latest = latest_row.revision if latest_row is not None else 0
    if payload.expected_revision != latest:
        raise ManualJournalConflict("版本冲突：请刷新手工台账后重新核对")
    if latest_row is not None and payload.observed_at < datetime.fromisoformat(
        latest_row.observed_at
    ):
        raise ValueError("账户观察时间不得早于上一个版本")
    lots = [{
        "symbol": lot.symbol,
        "quantity": _decimal_text(lot.quantity),
        "paid_amount": _decimal_text(lot.paid_amount) if lot.paid_amount is not None else None,
        "bought_at": lot.bought_at.isoformat() if lot.bought_at is not None else None,
    } for lot in payload.lots]
    operation = None
    if payload.operation is not None:
        entry = payload.operation
        operation = {
            "side": entry.side,
            "symbol": entry.symbol,
            "quantity": _decimal_text(entry.quantity),
            "price": _decimal_text(entry.price),
            "executed_at": entry.executed_at.isoformat(),
            "fee": _decimal_text(entry.fee) if entry.fee is not None else None,
        }
    row = ManualJournalRevision(
        revision=latest + 1,
        recorded_at=datetime.now(UTC).isoformat(),
        observed_at=payload.observed_at.isoformat(),
        available_cash=payload.available_cash,
        total_equity=payload.total_equity,
        lots=lots,
        operation=operation,
        note=payload.note,
    )
    session.add(row)
    session.flush()
    return _record_view(row)


def apply_manual_operation(session: Session, payload: ManualOperationApply) -> dict[str, object]:
    """Derive the next self-reported lot snapshot without touching formal fills."""
    latest = session.scalar(select(ManualJournalRevision).order_by(
        ManualJournalRevision.revision.desc()
    ).limit(1))
    if latest is None:
        raise ValueError("请先登记当前仓位")
    if latest.revision != payload.expected_revision:
        raise ManualJournalConflict("版本冲突：请刷新手工台账后重新核对")
    # Later backfilled trades may precede the user's current observation time.
    # A manual correction instead resets the chronology anchor to its observation.
    prior_time = (latest.operation["executed_at"] if latest.operation is not None
                  else latest.observed_at)
    if payload.operation.executed_at <= datetime.fromisoformat(prior_time):
        raise ValueError("操作时间须晚于上一笔操作或最近一次人工校正")
    if payload.operation.executed_at > payload.observed_at:
        raise ValueError("操作时间不得晚于本次账户观察时间")

    lots = [dict(lot) for lot in latest.lots]
    operation = payload.operation
    if operation.side == "BUY":
        if payload.sell_lot_index is not None or payload.sell_allocations is not None:
            raise ValueError("买入不得指定卖出批次")
        paid_amount = None
        if operation.fee is not None:
            with localcontext() as context:
                context.prec = 64
                amount = operation.quantity * operation.price + operation.fee
            try:
                _money(amount, positive=True)
                paid_amount = _decimal_text(amount)
            except ValueError:
                # Preserve quantity and execution, but never round a cost fact.
                pass
        lots.append({
            "symbol": operation.symbol,
            "quantity": _decimal_text(operation.quantity),
            "paid_amount": paid_amount,
            "bought_at": operation.executed_at.isoformat(),
        })
    else:
        if payload.sell_lot_index is not None and payload.sell_allocations is not None:
            raise ValueError("同一卖出不能同时使用两种批次分配方式")
        allocations = payload.sell_allocations
        if allocations is None and payload.sell_lot_index is not None:
            allocations = [ManualSellAllocation(
                lot_index=payload.sell_lot_index, quantity=operation.quantity)]
        if not allocations:
            raise ValueError("请选择被卖出的持仓批次")
        if (len({item.lot_index for item in allocations}) != len(allocations)
                or sum((item.quantity for item in allocations), Decimal(0)) != operation.quantity):
            raise ValueError("卖出批次重复或扣减总量与成交数量不一致")
        remove_indices = []
        for item in allocations:
            if item.lot_index >= len(lots):
                raise ValueError("卖出批次不存在")
            lot = lots[item.lot_index]
            if lot["symbol"] != operation.symbol:
                raise ValueError("卖出证券与持仓批次不一致")
            remaining = Decimal(lot["quantity"]) - item.quantity
            if remaining < 0:
                raise ValueError("卖出数量超过所选持仓批次")
            if remaining == 0:
                remove_indices.append(item.lot_index)
            else:
                lot["quantity"] = _decimal_text(remaining)
                # The correct remaining cost basis is not inferable from a sale alone.
                lot["paid_amount"] = None
        for index in sorted(remove_indices, reverse=True):
            lots.pop(index)

    next_report = ManualJournalWrite(
        expected_revision=payload.expected_revision,
        observed_at=payload.observed_at,
        available_cash=payload.available_cash,
        total_equity=payload.total_equity,
        lots=lots,
        operation=operation,
        note=payload.note,
    )
    return append_manual_record(session, next_report)


def read_manual_records(session: Session) -> dict[str, object]:
    """Read recent self-reports with explicit provenance; no formal overview mutation."""
    rows = list(session.scalars(select(ManualJournalRevision).order_by(
        ManualJournalRevision.revision.desc()
    ).limit(20)))
    # Revisions are contiguous and append-only. A separate COUNT under READ COMMITTED
    # could observe a newer concurrent append than the rows selected above.
    total = rows[0].revision if rows else 0
    return {
        "schema_version": "m8.manual_journal.v1",
        "source": "user_manual",
        "notice": "仅为用户手工记录，未与券商核对；不代表实时账户、可卖数量或交易许可。",
        "latest_revision": rows[0].revision if rows else 0,
        "total_revisions": total,
        "latest": _record_view(rows[0]) if rows else None,
        "history": [_record_view(row) for row in rows],
        "realtime": False,
        "broker_reconciled": False,
        "full_account_verified": False,
        "trade_execution_enabled": False,
    }
