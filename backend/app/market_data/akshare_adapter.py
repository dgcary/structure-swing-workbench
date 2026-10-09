"""AKShare implementation of the provider-neutral market-data interface.

AKShare is imported lazily; deterministic tests inject a fake client.
No timestamp is invented when a source omits its observation time.
"""
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from app.market_data.contracts import (
    Bar, DataQuality, DataResult, Quote, SecurityInfo, Timeframe, quality_at,
)

CHINA = ZoneInfo("Asia/Shanghai")
QUOTE_COLUMNS = {
    "name": "名称", "last": "最新价", "previous_close": "昨收",
    "open": "今开", "high": "最高", "low": "最低",
    "change_pct": "涨跌幅", "limit_up": "涨停价",
    "limit_down": "跌停价", "volume": "成交量",
    "amount": "成交额", "turnover_pct": "换手率",
    "amplitude_pct": "振幅",
}
BAR_COLUMNS = {
    "open": "开盘", "high": "最高", "low": "最低", "close": "收盘",
    "volume": "成交量", "amount": "成交额",
}


MISSING_MARKERS = {"", "nan", "nat", "none", "null", "--", "-", "—", "n/a"}


def _is_missing(value: Any) -> bool:
    return value is None or str(value).strip().lower() in MISSING_MARKERS


def _decimal(value: Any) -> Decimal | None:
    if _is_missing(value):
        return None
    try:
        result = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid numeric value: {value}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite numeric value: {value}")
    return result


def _timestamp(value: Any) -> datetime | None:
    if _is_missing(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid source timestamp: {value}") from exc
    return parsed.replace(tzinfo=CHINA) if parsed.tzinfo is None else parsed


class AKShareProvider:
    source = "AKShare"

    def __init__(
        self,
        client: Any = None,
        clock: Callable[[], datetime] | None = None,
        quote_max_age: timedelta = timedelta(minutes=15),
        bar_max_age: timedelta = timedelta(minutes=45),
    ) -> None:
        if client is None:
            import akshare  # optional external dependency, never imported by core modules

            client = akshare
        self.client = client
        self.clock = clock or (lambda: datetime.now(CHINA))
        self.quote_max_age = quote_max_age
        self.bar_max_age = bar_max_age

    def _result(
        self, value: Any, fetched: datetime, observed: datetime | None,
        missing: tuple[str, ...] = (), error: str | None = None,
    ) -> DataResult[Any]:
        if error:
            quality = DataQuality.ERROR
        elif value is None:
            quality = DataQuality.MISSING
        else:
            quality = quality_at(observed, fetched, self.quote_max_age)
        return DataResult(
            value=value, source=self.source, fetched_at=fetched,
            observed_at=observed, quality=quality,
            missing_fields=missing, error=error,
        )

    def get_quote(self, symbol: str) -> DataResult[Quote]:
        fetched = self.clock()
        try:
            rows = self.client.stock_zh_a_spot_em().to_dict("records")
            record = next(
                (row for row in rows if str(row.get("代码", "")).zfill(6) == symbol), None
            )
            if record is None:
                return self._result(None, fetched, None, ("symbol",))
            values: dict[str, Any] = {"symbol": symbol}
            for key, column in QUOTE_COLUMNS.items():
                raw = record.get(column)
                values[key] = (None if _is_missing(raw) else str(raw)) if key == "name" else _decimal(raw)
            values["close"] = values["last"]
            for key in ("last", "previous_close", "open", "high", "low", "limit_up", "limit_down"):
                if values[key] is not None and values[key] < 0:
                    raise ValueError(f"quote {key} is negative")
            if values["high"] is not None and values["low"] is not None:
                if values["high"] < values["low"]:
                    raise ValueError("quote high is below low")
                for key in ("open", "last"):
                    if values[key] is not None and not (
                        values["low"] <= values[key] <= values["high"]
                    ):
                        raise ValueError(f"quote {key} is outside high/low")
            for key in ("volume", "amount", "turnover_pct", "amplitude_pct"):
                if values[key] is not None and values[key] < 0:
                    raise ValueError(f"quote {key} is negative")
            if (
                values["limit_up"] is not None
                and values["limit_down"] is not None
                and values["limit_down"] > values["limit_up"]
            ):
                raise ValueError("quote limit_down exceeds limit_up")
            quote = Quote(**values)
            observed = _timestamp(record.get("更新时间") or record.get("时间"))
            missing = tuple(f.name for f in fields(Quote)
                            if getattr(quote, f.name) is None)
            return self._result(quote, fetched, observed, missing)
        except Exception as exc:
            return self._result(None, fetched, None, error=f"{type(exc).__name__}: {exc}")

    def get_bars(self, symbol: str, timeframe: Timeframe) -> DataResult[tuple[Bar, ...]]:
        fetched = self.clock()
        if not isinstance(timeframe, Timeframe):
            return self._result(None, fetched, None, error="unsupported timeframe")
        try:
            if timeframe is Timeframe.DAY:
                frame = self.client.stock_zh_a_hist(
                    symbol=symbol, period="daily", adjust=""
                )
            else:
                period = "5" if timeframe is Timeframe.MIN5 else "15"
                frame = self.client.stock_zh_a_hist_min_em(
                    symbol=symbol, period=period, adjust=""
                )
            records = frame.to_dict("records")
            if not records:
                return self._result(None, fetched, None, ("bars",))
            bars = []
            for row in records:
                timestamp = _timestamp(row.get("时间") or row.get("日期"))
                if timestamp is None:
                    raise ValueError("bar observation date/time missing")
                values = {key: _decimal(row.get(column))
                          for key, column in BAR_COLUMNS.items()}
                if any(values[key] is None for key in ("open", "high", "low", "close")):
                    raise ValueError("bar OHLC contains invalid values")
                for key in ("open", "high", "low", "close"):
                    if values[key] < 0:
                        raise ValueError(f"bar {key} is negative")
                if values["high"] < values["low"]:
                    raise ValueError("bar high is below low")
                if not values["low"] <= values["open"] <= values["high"]:
                    raise ValueError("bar open is outside high/low")
                if not values["low"] <= values["close"] <= values["high"]:
                    raise ValueError("bar close is outside high/low")
                for key in ("volume", "amount"):
                    if values[key] is not None and values[key] < 0:
                        raise ValueError(f"bar {key} is negative")
                bars.append(Bar(observed_at=timestamp, **values))
            bars.sort(key=lambda bar: bar.observed_at)
            if any(left.observed_at == right.observed_at
                   for left, right in pairwise(bars)):
                raise ValueError("duplicate bar observation timestamp")
            # Daily AKShare bars provide dates, not reliable intraday observation times.
            observed = None if timeframe is Timeframe.DAY else bars[-1].observed_at
            quality = (
                DataQuality.UNVERIFIED if observed is None
                else quality_at(observed, fetched, self.bar_max_age)
            )
            missing = tuple(
                field for field in ("volume", "amount")
                if any(getattr(bar, field) is None for bar in bars)
            )
            return DataResult(
                value=tuple(bars), source=self.source, fetched_at=fetched,
                observed_at=observed, quality=quality, missing_fields=missing,
            )
        except Exception as exc:
            return self._result(None, fetched, None, error=f"{type(exc).__name__}: {exc}")

    def get_security(self, symbol: str) -> DataResult[SecurityInfo]:
        quote_result = self.get_quote(symbol)
        if quote_result.value is None:
            return DataResult(
                value=None, source=self.source, fetched_at=quote_result.fetched_at,
                observed_at=quote_result.observed_at, quality=quote_result.quality,
                missing_fields=quote_result.missing_fields, error=quote_result.error,
            )
        name = quote_result.value.name
        st = name.upper().startswith(("ST", "*ST", "S*ST")) if name else None
        details: dict[str, Any] = {}
        detail_error = None
        try:
            rows = self.client.stock_individual_info_em(symbol=symbol).to_dict("records")
            details = {str(row.get("item")): row.get("value") for row in rows}
        except Exception as exc:
            detail_error = f"security details unavailable: {type(exc).__name__}: {exc}"
        industry = details.get("行业")
        exchange = details.get("交易所") or details.get("上市交易所")
        info = SecurityInfo(
            symbol=symbol, name=name,
            industry=str(industry) if industry is not None else None,
            exchange=str(exchange) if exchange is not None else None,
            is_st=st,
        )
        missing = tuple(
            field.name for field in fields(SecurityInfo)
            if getattr(info, field.name) is None
        )
        return DataResult(
            value=info, source=self.source, fetched_at=quote_result.fetched_at,
            observed_at=quote_result.observed_at,
            quality=DataQuality.ERROR if detail_error else quote_result.quality,
            missing_fields=missing, error=detail_error,
        )
