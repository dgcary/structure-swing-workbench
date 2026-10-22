"""Read-only validation of a CSV against an isolated M5 ledger."""

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.account.csv_ingest import SCHEMAS, import_csv
from app.account.imports import parse_rows
from app.account.ledger import AccountLedger


class CSVPreviewRequest(BaseModel):
    kind: Literal["fills", "holdings", "account"]
    data: str = Field(min_length=1, max_length=500_000)


def preview_csv(payload: CSVPreviewRequest) -> dict[str, object]:
    """Check input without persisting or reconciling against live holdings."""
    try:
        rows = parse_rows(payload.data, SCHEMAS[payload.kind])
        result = import_csv(
            AccountLedger(), payload.kind, payload.data, batch_id="preview-only"
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "schema_version": "m8.csv_preview.v1",
        "kind": payload.kind,
        "row_count": len(rows),
        "new_facts_in_isolated_preview": result.imported,
        "duplicates_in_isolated_preview": result.duplicates,
        "conflicts_in_isolated_preview": result.conflicts,
        "valid_csv_structure": True,
        "persisted": False,
        "reconciled_with_live_account": False,
        "trade_execution_enabled": False,
        "notice": "仅校验 CSV 格式及空白隔离账本内部一致性；未核对真实账户、未保存或导入。",
    }
