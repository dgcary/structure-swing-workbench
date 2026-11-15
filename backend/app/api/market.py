"""Read-only market-data endpoints backed by the lazy AKShare adapter.

The adapter imports akshare lazily; when the optional dependency is missing the
API answers with an explicit 503 instead of a silent failure.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_market_provider
from app.market_data.contracts import DataResult, Timeframe

router = APIRouter(tags=["market"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _result_dto(result: DataResult[Any]) -> dict[str, Any]:
    value = result.value
    if value is None:
        payload = None
    elif isinstance(value, tuple):
        payload = [_json_safe(asdict(item) if is_dataclass(item) else item) for item in value]
    else:
        payload = _json_safe(asdict(value) if is_dataclass(value) else value)
    return {
        "value": payload,
        "source": result.source,
        "fetched_at": _json_safe(result.fetched_at),
        "observed_at": _json_safe(result.observed_at),
        "quality": result.quality.value,
        "missing_fields": list(result.missing_fields),
        "error": result.error,
    }


def _unavailable(exc: ImportError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="行情依赖 akshare 未安装，请在部署环境安装 market 可选依赖后重试",
    )


@router.get("/market/quote/{symbol}")
def quote(symbol: str, provider: Any = Depends(get_market_provider)) -> dict:
    try:
        result = provider.get_quote(symbol)
    except ImportError as exc:
        raise _unavailable(exc) from exc
    return _result_dto(result)


@router.get("/market/bars/{symbol}")
def bars(symbol: str, timeframe: Timeframe = Timeframe.DAY, provider: Any = Depends(get_market_provider)) -> dict:
    try:
        result = provider.get_bars(symbol, timeframe)
    except ImportError as exc:
        raise _unavailable(exc) from exc
    return _result_dto(result)


@router.get("/market/security/{symbol}")
def security(symbol: str, provider: Any = Depends(get_market_provider)) -> dict:
    try:
        result = provider.get_security(symbol)
    except ImportError as exc:
        raise _unavailable(exc) from exc
    return _result_dto(result)
