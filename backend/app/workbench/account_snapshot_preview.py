"""Isolated, user-supplied CSV overview. No account data is retained between requests."""

from datetime import UTC, date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from app.account.csv_ingest import import_csv
from app.account.ledger import AccountLedger
from app.workbench.overview import build_overview

MARKET_TZ = timezone(timedelta(hours=8))


class DailyFillCoverageClaim(BaseModel):
    """Untrusted CSV export claim, NOT a broker-authenticated completeness watermark."""

    market_date: date
    exported_at: datetime
    complete_through: datetime
    export_reference: str = Field(min_length=1, max_length=128)
    expected_fill_ids: list[str] = Field(max_length=10_000)
    declared_full_day: bool = False

    @model_validator(mode="after")
    def check_claim(self) -> "DailyFillCoverageClaim":
        if any(stamp.tzinfo is None or stamp.utcoffset() is None
               for stamp in (self.exported_at, self.complete_through)):
            raise ValueError("成交清单导出时间和覆盖水位必须包含时区")
        if self.complete_through > self.exported_at:
            raise ValueError("成交覆盖水位不得晚于导出时间")
        if not self.export_reference.strip():
            raise ValueError("成交清单导出标识不能为空")
        if any(not identifier.strip() or identifier != identifier.strip()
               for identifier in self.expected_fill_ids):
            raise ValueError("成交清单编号不能为空或包含首尾空格")
        if len(set(self.expected_fill_ids)) != len(self.expected_fill_ids):
            raise ValueError("成交清单编号重复，无法核对完整性")
        return self


def _preview_daily_fill_coverage(
    ledger: AccountLedger, claim: DailyFillCoverageClaim, duplicate_rows: int,
    *, now: datetime | None = None,
) -> dict[str, object]:
    """Compare claimed IDs with uploaded fills; never certify broker completeness."""
    now = now or datetime.now(UTC)
    if (
        claim.exported_at.astimezone(UTC) > now + timedelta(minutes=5)
        or claim.complete_through.astimezone(UTC) > now + timedelta(minutes=5)
        or claim.market_date > now.astimezone(MARKET_TZ).date()
    ):
        raise ValueError("成交清单日期或覆盖水位在未来，不能作为已发生事实")
    day_fills = [
        fill for fill in ledger.fills.values()
        if fill.executed_at.astimezone(MARKET_TZ).date() == claim.market_date
    ]
    recorded = {fill.fill_id for fill in day_fills}
    # A self-reported watermark cannot cover a fill executed after that instant.
    # Count such rows even when the self-reported ID set matches exactly.
    outside_watermark = sum(
        fill.executed_at.astimezone(UTC) > claim.complete_through.astimezone(UTC)
        for fill in day_fills
    )
    expected = set(claim.expected_fill_ids)
    missing = expected - recorded
    unexpected = recorded - expected
    market_close = datetime.combine(claim.market_date, time(15), tzinfo=MARKET_TZ)
    claimed_full_day = (
        claim.declared_full_day
        # A-share exchanges do not have regular weekend trading sessions.
        # Without an authenticated exchange calendar, a weekend self-claim
        # cannot be labelled as a complete market day.
        and claim.market_date.weekday() < 5
        # A watermark for a later market day cannot certify this day's
        # self-reported manifest, even when its IDs happen to match.
        and claim.complete_through.astimezone(MARKET_TZ).date() == claim.market_date
        and claim.complete_through.astimezone(UTC) >= market_close.astimezone(UTC)
        # A five-minute clock-skew allowance must not turn a future close or
        # future export into an already completed market day.
        and now.astimezone(UTC) >= market_close.astimezone(UTC)
        and claim.exported_at.astimezone(UTC) <= now.astimezone(UTC)
        and claim.complete_through.astimezone(UTC) <= now.astimezone(UTC)
        and bool(expected)
    )
    mismatch = bool(missing or unexpected or duplicate_rows or outside_watermark)
    status = (
        "mismatch" if mismatch else
        "matched_unverified" if claimed_full_day else "insufficient"
    )
    warning = (
        "上传成交与自报清单编号不一致、CSV 重复，或存在晚于自报水位的成交；"
        "必须核对原始券商流水。"
        if mismatch else
        "上传成交与自报清单编号一致，但日期可能非交易日、未到实际收盘、导出/覆盖时间尚未发生，或缺少完整覆盖声明/有效成交；不能认证当日T次数。"
        if not claimed_full_day else
        "仅与用户自报成交清单逐笔编号一致；没有独立券商来源认证，"
        "不能证明全量成交、当日T次数、未闭环T或T+1可卖数量。"
    )
    return {
        "status": status,
        "market_date": claim.market_date.isoformat(),
        "export_reference": claim.export_reference,
        "claimed_complete_through": claim.complete_through.isoformat(),
        "recorded_fill_count": len(recorded),
        "declared_fill_count": len(expected),
        "missing_fill_count": len(missing),
        "unexpected_fill_count": len(unexpected),
        "duplicate_csv_rows": duplicate_rows,
        "outside_watermark_fill_count": outside_watermark,
        "broker_reconciled": False,
        "trade_execution_enabled": False,
        "warning": warning,
    }


class AccountSnapshotPreviewRequest(BaseModel):
    account: str | None = Field(default=None, max_length=500_000)
    holdings: str | None = Field(default=None, max_length=500_000)
    fills: str | None = Field(default=None, max_length=500_000)
    daily_fill_claim: DailyFillCoverageClaim | None = None

    @model_validator(mode="after")
    def require_data(self) -> "AccountSnapshotPreviewRequest":
        if not any(value is not None and value.strip() for value in (
            self.account, self.holdings, self.fills
        )):
            raise ValueError("至少提供一类账户、持仓或成交 CSV")
        if self.daily_fill_claim is not None and not (self.fills and self.fills.strip()):
            raise ValueError("提供成交清单覆盖声明时必须同时上传成交 CSV")
        return self


def preview_account_snapshot(data: AccountSnapshotPreviewRequest) -> dict[str, object]:
    """Reconcile supplied CSVs in a fresh ledger; never imply a live account."""
    ledger = AccountLedger()
    row_counts: dict[str, int] = {}
    duplicate_fill_rows = 0
    try:
        for kind in ("account", "holdings", "fills"):
            csv_data = getattr(data, kind)
            if csv_data is None:
                continue
            result = import_csv(ledger, kind, csv_data, batch_id=f"preview-{kind}")
            row_counts[kind] = result.imported + result.duplicates
            if kind == "fills":
                duplicate_fill_rows = result.duplicates
        if ledger.conflicts:
            raise ValueError("上传的账户事实存在冲突，请核对来源和时间")
        # Future timestamps cannot authenticate observed account or fill facts.
        # Reject the entire disposable M8 preview; do not alter the M5 ledger.
        latest_allowed = datetime.now(UTC) + timedelta(minutes=5)
        if any(fact.observed_at.astimezone(UTC) > latest_allowed
               for fact in ledger.facts.values()) or any(
            fill.executed_at.astimezone(UTC) > latest_allowed
            for fill in ledger.fills.values()
        ):
            raise ValueError("上传的账户、持仓或成交 CSV 包含未来时间，无法作为已发生事实展示")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        daily_coverage = (
            _preview_daily_fill_coverage(ledger, data.daily_fill_claim, duplicate_fill_rows)
            if data.daily_fill_claim is not None else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    overview = build_overview(ledger)
    overview.update({
        "schema_version": "m8.account_snapshot_preview.v1",
        "mode": "isolated_csv_preview",
        "input_source": "user_uploaded_csv",
        "imported_kinds": list(row_counts),
        "persisted": False,
        "realtime": False,
        "full_account_verified": False,
        "daily_fill_coverage": daily_coverage,
        "trade_execution_enabled": False,
        "notice": (
            "仅根据本次上传的 CSV 临时展示账户及持仓事实；"
            "不保存、不接入券商、不保证账户完整或实时，不授权交易。"
        ),
    })
    return overview
