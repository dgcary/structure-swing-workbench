"""Isolated, user-supplied CSV overview. No account data is retained between requests."""

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from app.account.csv_ingest import import_csv
from app.account.ledger import AccountLedger
from app.workbench.overview import build_overview


class AccountSnapshotPreviewRequest(BaseModel):
    account: str | None = Field(default=None, max_length=500_000)
    holdings: str | None = Field(default=None, max_length=500_000)
    fills: str | None = Field(default=None, max_length=500_000)

    @model_validator(mode="after")
    def require_data(self) -> "AccountSnapshotPreviewRequest":
        if not any(value is not None and value.strip() for value in (
            self.account, self.holdings, self.fills
        )):
            raise ValueError("至少提供一类账户、持仓或成交 CSV")
        return self


def preview_account_snapshot(data: AccountSnapshotPreviewRequest) -> dict[str, object]:
    """Reconcile supplied CSVs in a fresh ledger; never imply a live account."""
    ledger = AccountLedger()
    row_counts: dict[str, int] = {}
    try:
        for kind in ("account", "holdings", "fills"):
            csv_data = getattr(data, kind)
            if csv_data is None:
                continue
            result = import_csv(ledger, kind, csv_data, batch_id=f"preview-{kind}")
            row_counts[kind] = result.imported + result.duplicates
        if ledger.conflicts:
            raise ValueError("上传的账户事实存在冲突，请核对来源和时间")
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
        "trade_execution_enabled": False,
        "notice": (
            "仅根据本次上传的 CSV 临时展示账户及持仓事实；"
            "不保存、不接入券商、不保证账户完整或实时，不授权交易。"
        ),
    })
    return overview
