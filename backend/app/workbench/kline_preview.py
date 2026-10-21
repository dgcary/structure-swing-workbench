"""M8 read-only OHLCV CSV preview; no market lookup or trading judgment."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

COLUMNS = ("time", "open", "high", "low", "close", "volume")
MAX_BARS = 500
DAY_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
MINUTE_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


class KlinePreviewRequest(BaseModel):
    timeframe: Literal["day", "5m", "15m"]
    data: str = Field(min_length=1, max_length=250_000)


def _number(raw: str | None, *, positive: bool) -> Decimal:
    try:
        value = Decimal(raw.strip() if raw is not None else "")
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("价格或成交量不是有效数字") from exc
    if not value.is_finite() or (value <= 0 if positive else value < 0):
        raise ValueError("价格必须大于零，成交量必须非负且均为有限数字")
    return value


def _time(raw: str | None, timeframe: str) -> str:
    if not raw or not raw.strip():
        raise ValueError("K线时间不能为空")
    value = raw.strip()
    try:
        if timeframe == "day":
            if not DAY_STAMP.fullmatch(value):
                raise ValueError("日K必须使用 YYYY-MM-DD")
            return date.fromisoformat(value).isoformat()
        if not MINUTE_STAMP.fullmatch(value):
            raise ValueError("分钟K必须使用带时区的 ISO 时间")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("分钟K必须带时区")
        return parsed.isoformat()
    except ValueError as exc:
        raise ValueError("K线时间格式无效：日K用日期，分钟K用带时区时间") from exc


def preview_kline(payload: KlinePreviewRequest) -> dict[str, object]:
    """Validate uploaded bars and preserve their provenance as user input only."""
    try:
        reader = csv.DictReader(io.StringIO(payload.data, newline=""), strict=True)
        if reader.fieldnames is None or tuple(reader.fieldnames) != COLUMNS:
            raise ValueError("CSV表头必须依次为 time,open,high,low,close,volume")
        bars: list[dict[str, str]] = []
        previous: str | None = None
        for row in reader:
            if len(bars) >= MAX_BARS:
                raise ValueError("单次最多预览500根K线")
            if None in row or any(row.get(col) is None for col in COLUMNS):
                raise ValueError("K线列数不正确")
            stamp = _time(row["time"], payload.timeframe)
            if previous is not None and (
                stamp <= previous if payload.timeframe == "day" else
                datetime.fromisoformat(stamp) <= datetime.fromisoformat(previous)
            ):
                raise ValueError("K线时间必须严格递增且不可重复")
            previous = stamp
            values = {key: _number(row[key], positive=key != "volume")
                      for key in COLUMNS[1:]}
            if values["high"] < max(values["open"], values["close"], values["low"]):
                raise ValueError("最高价不能低于开盘、收盘或最低价")
            if values["low"] > min(values["open"], values["close"]):
                raise ValueError("最低价不能高于开盘或收盘")
            bars.append({"time": stamp, **{key: str(value)
                                          for key, value in values.items()}})
        if not bars:
            raise ValueError("CSV没有K线数据")
    except (ValueError, csv.Error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "schema_version": "m8.kline_preview.v1",
        "timeframe": payload.timeframe,
        "source": "user_uploaded_csv",
        "last_observation": bars[-1]["time"],
        "bar_count": len(bars),
        "bars": bars,
        "persisted": False,
        "realtime": False,
        "setup_detected": False,
        "trade_execution_enabled": False,
        "notice": "仅显示用户上传的历史OHLCV；未核验行情来源或实时性，不识别结构/Setup，不生成交易指令。",
    }
