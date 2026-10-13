"""Strict CSV input parsing for account snapshots and transactions."""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_number(value: str, label: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{label}不是有效数字") from exc
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError(f"{label}必须是有限非负数" if not positive else f"{label}必须大于0")
    return number


def parse_time(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError("时间格式必须为 ISO8601") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return instant


def parse_rows(data: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(data.lstrip("\ufeff")))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("CSV 表头缺失或重复")
    missing = set(required) - set(reader.fieldnames)
    if missing:
        raise ValueError(f"CSV 缺少字段：{', '.join(sorted(missing))}")
    rows = list(reader)
    if not rows:
        raise ValueError("CSV 不能为空")
    for row in rows:
        if None in row or any(not (row.get(k) or "").strip() for k in required):
            raise ValueError("CSV 行缺少必填值或包含多余字段")
    return rows
