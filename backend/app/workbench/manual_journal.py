"""Versioned user-entered account notes, isolated from broker and formal facts."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ManualJournalRevision


def _money(value: Decimal | None, *, positive: bool = False, price: bool = False) -> Decimal | None:
    if value is None:
        return None
    upper = Decimal("1e14") if price else Decimal("1e16")
    if (not value.is_finite() or value < 0 or (positive and value == 0)
            or value >= upper or value.normalize().as_tuple().exponent < -4):
        raise ValueError("金额、价格或数量必须为有效的四位小数内数值")
    return value


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
        if (self.available_cash is None and self.total_equity is None
                and not self.lots and self.operation is None):
            raise ValueError("请至少填写一项账户或操作记录")
        if any(lot.bought_at is not None and lot.bought_at > self.observed_at
               for lot in self.lots):
            raise ValueError("买入时间不得晚于账户观察时间")
        if self.operation and self.operation.executed_at > self.observed_at:
            raise ValueError("操作时间不得晚于账户观察时间")
        return self


def _record_view(row: ManualJournalRevision) -> dict[str, object]:
    return {
        "id": row.id,
        "revision": row.revision,
        "recorded_at": row.recorded_at,
        "observed_at": row.observed_at,
        "available_cash": str(row.available_cash) if row.available_cash is not None else None,
        "total_equity": str(row.total_equity) if row.total_equity is not None else None,
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
    return format(value.normalize(), "f")


def append_manual_record(session: Session, payload: ManualJournalWrite) -> dict[str, object]:
    """Append one whole self-report; unique revision prevents silent concurrent overwrites."""
    latest = session.scalar(select(func.max(ManualJournalRevision.revision))) or 0
    if payload.expected_revision != latest:
        raise ValueError("版本冲突：请刷新手工台账后重新核对")
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


def read_manual_records(session: Session) -> dict[str, object]:
    """Read recent self-reports with explicit provenance; no formal overview mutation."""
    rows = list(session.scalars(select(ManualJournalRevision).order_by(
        ManualJournalRevision.revision.desc()
    ).limit(20)))
    total = session.scalar(select(func.count()).select_from(ManualJournalRevision)) or 0
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
