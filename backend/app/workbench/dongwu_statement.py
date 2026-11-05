"""Read-only Dongwu PDF statement consistency checks.

The PDF has date-only execution rows and no independently verified execution
identifier or timestamp. Even a perfect internal comparison is not a broker
completeness watermark, live position, T+1 inventory, or trading permission.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Literal


@dataclass(frozen=True, slots=True)
class StatementCheck:
    status: Literal["matched_unverified", "mismatch"]
    period_start: date
    period_end: date
    summary_row_count: int
    detail_row_count: int
    matched_group_count: int
    missing_summary_group_count: int
    extra_summary_group_count: int
    mismatched_group_count: int
    repaired_summary_rows: int
    broker_reconciled: bool = False
    full_account_verified: bool = False
    trade_execution_enabled: bool = False
    execution_ids_available: bool = False
    execution_times_available: bool = False
    footer_totals_checked: bool = False
    footer_totals_mismatched_count: int = 0


def _text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def _number(value: str | None, label: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(_text(value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"{label}无法解析") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError(f"{label}不是有效有限数值")
    return result


def _group_key(row: Sequence[str | None], start: date, end: date) -> tuple[date, str, str, str, str]:
    token = _text(row[0])
    if not re.fullmatch(r"20\d{6}", token):
        raise ValueError("成交日期不是八位年月日")
    try:
        day = datetime.strptime(token, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("成交日期无效") from exc
    if not start <= day <= end:
        raise ValueError("成交日期超出对账单周期")
    exchange, currency, side, symbol = (_text(row[i]) for i in (1, 2, 3, 4))
    if not exchange or not currency or not symbol or side not in {"买入", "卖出"}:
        raise ValueError("交易所、币种、方向或证券代码缺失")
    return day, exchange, currency, side, symbol


def _group_values(
    rows: Sequence[Sequence[str | None]], *, width: int,
    indexes: tuple[int, int, int, int, int], start: date, end: date,
) -> dict[tuple[date, str, str, str, str], tuple[Decimal, ...]]:
    groups: dict[tuple[date, str, str, str, str], list[Decimal]] = defaultdict(
        lambda: [Decimal(0) for _ in indexes]
    )
    for row in rows:
        if len(row) != width:
            raise ValueError("成交表列数与东吴对账单格式不符")
        key = _group_key(row, start, end)
        values = tuple(
            _number(row[index], "成交数量" if position == 0 else "金额或费用",
                    positive=position == 0)
            for position, index in enumerate(indexes)
        )
        for position, value in enumerate(values):
            groups[key][position] += value
    return {key: tuple(values) for key, values in groups.items()}


def _footer_mismatches(
    rows: Sequence[Sequence[str | None]], totals: Sequence[Sequence[str | None]],
    *, value_columns: tuple[int, ...], total_columns: tuple[int, ...],
) -> int:
    expected: dict[str, list[Decimal]] = defaultdict(
        lambda: [Decimal(0) for _ in value_columns]
    )
    for row in rows:
        currency = _text(row[2])
        for offset, column in enumerate(value_columns):
            expected[currency][offset] += _number(row[column], "成交金额或费用")
    observed: dict[str, tuple[Decimal, ...]] = {}
    for row in totals:
        currency = _text(row[2])
        if currency in observed:
            raise ValueError("同一币种出现重复成交合计")
        observed[currency] = tuple(_number(row[column], "合计金额或费用")
                                   for column in total_columns)
    return sum(
        currency not in observed or tuple(values) != observed[currency]
        for currency, values in expected.items()
    ) + sum(
        any(value != 0 for value in values)
        for currency, values in observed.items() if currency not in expected
    )


def compare_statement_rows(
    summary_rows: Sequence[Sequence[str | None]],
    detail_rows: Sequence[Sequence[str | None]],
    *, period_start: date, period_end: date, repaired_rows: int,
    summary_totals: Sequence[Sequence[str | None]] | None = None,
    detail_totals: Sequence[Sequence[str | None]] | None = None,
) -> StatementCheck:
    """Compare grouped statement figures exactly; return no private row values."""
    if period_start > period_end or repaired_rows < 0:
        raise ValueError("对账单周期或修复行数无效")
    if not detail_rows:
        raise ValueError("无可核对的成交明细；不能推断零成交")
    summary = _group_values(
        summary_rows, width=11, indexes=(6, 7, 8, 9, 10),
        start=period_start, end=period_end,
    )
    detail = _group_values(
        detail_rows, width=14, indexes=(6, 8, 9, 10, 11),
        start=period_start, end=period_end,
    )
    summary_keys, detail_keys = set(summary), set(detail)
    common = summary_keys & detail_keys
    changed = sum(summary[key] != detail[key] for key in common)
    missing = len(detail_keys - summary_keys)
    extra = len(summary_keys - detail_keys)
    if bool(summary_totals) != bool(detail_totals):
        raise ValueError("成交汇总与交割明细的合计行不完整")
    totals_checked = bool(summary_totals) and bool(detail_totals)
    total_mismatches = (
        _footer_mismatches(
            summary_rows, summary_totals, value_columns=(7, 8, 9, 10),
            total_columns=(7, 8, 9, 10),
        ) + _footer_mismatches(
            detail_rows, detail_totals, value_columns=(8, 9, 10, 11, 12),
            total_columns=(8, 9, 10, 11, 12),
        ) if totals_checked else 0
    )
    return StatementCheck(
        status="mismatch" if missing or extra or changed or total_mismatches
        else "matched_unverified",
        period_start=period_start, period_end=period_end,
        summary_row_count=len(summary_rows), detail_row_count=len(detail_rows),
        matched_group_count=len(common) - changed,
        missing_summary_group_count=missing,
        extra_summary_group_count=extra,
        mismatched_group_count=changed,
        repaired_summary_rows=repaired_rows,
        footer_totals_checked=totals_checked,
        footer_totals_mismatched_count=total_mismatches,
    )


def _statement_period(first_page_text: str) -> tuple[date, date]:
    compact = _text(first_page_text)
    if "东吴证券" not in compact or "对账单" not in compact:
        raise ValueError("不是可识别的东吴证券对账单")
    match = re.search(
        r"账单周期[:：](20\d{2})年(\d{1,2})月(\d{1,2})日[-—至]"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
        compact,
    )
    if match is None:
        raise ValueError("对账单周期无法核实")
    try:
        start = date(*(int(value) for value in match.groups()[:3]))
        end = date(*(int(value) for value in match.groups()[3:]))
    except ValueError as exc:
        raise ValueError("对账单周期日期无效") from exc
    if start > end:
        raise ValueError("对账单周期倒置")
    return start, end


def _header_kind(row: Sequence[str | None]) -> Literal["summary", "detail"] | None:
    if not row or _text(row[0]) != "成交日期":
        return None
    labels = tuple(_text(cell) for cell in row)
    if labels == (
        "成交日期", "交易所", "币种", "交易类别", "证券代码", "证券名称",
        "成交数量合计", "应收金额合计", "佣金合计", "印花税合计", "过户费合计",
    ):
        return "summary"
    if labels == (
        "成交日期", "交易所", "币种", "交易类别", "证券代码", "证券名称",
        "成交数量", "成交价格", "应收金额", "佣金", "印花税", "过户费",
        "其他费用", "股份余额",
    ):
        return "detail"
    return None


def _is_dated_row(row: Sequence[str | None]) -> bool:
    return bool(row) and bool(re.fullmatch(r"20\d{6}", _text(row[0])))


def _is_currency_total(
    row: Sequence[str | None], kind: Literal["summary", "detail"],
    *, continuation: bool,
) -> bool:
    first = _text(row[0])
    if first != "合计" and not (continuation and not first):
        return False
    amount_columns = (7, 8, 9, 10) if kind == "summary" else (8, 9, 10, 11, 12)
    if len(row) != (11 if kind == "summary" else 14) or not _text(row[2]):
        return False
    if any(_text(cell) for index, cell in enumerate(row)
           if index not in (0, 2, *amount_columns)):
        return False
    for column in amount_columns:
        _number(row[column], "合计金额或费用")
    return True


def _repair_summary_row(page, table, row_index: int, row: list[str | None]) -> list[str | None]:
    """Recover a visible page-first row whose right cell borders are missing.

    The following complete row supplies only x boundaries. All text comes
    from the missing cells' own y interval on the current page.
    """
    if row_index + 1 >= len(table.rows):
        raise ValueError("汇总表跨页行缺少可核实的列边界")
    current = table.rows[row_index].cells
    following = table.rows[row_index + 1].cells
    if (len(current) != 11 or len(following) != 11
            or current[0] is None or not all(cell is not None for cell in following)
            or not any(cell is None for cell in current)):
        raise ValueError("汇总表行缺失，无法安全恢复")
    y0, y1 = current[0][1], current[0][3]
    restored = list(row)
    for index, cell in enumerate(current):
        if cell is None:
            reference = following[index]
            box = (reference[0], y0, reference[2], y1)
            restored[index] = page.crop(box).extract_text() or ""
    if _number(restored[6], "跨页成交数量", positive=True) <= 0:
        raise ValueError("跨页汇总数量无效")
    return restored


def check_dongwu_statement_pdf(data: bytes) -> StatementCheck:
    """Read a Dongwu statement in memory; never persist or promote its rows."""
    if not isinstance(data, bytes) or not data or len(data) > 10_000_000:
        raise ValueError("对账单 PDF 为空或超过本地核对上限")
    import pdfplumber

    with pdfplumber.open(BytesIO(data)) as pdf:
        if not 1 <= len(pdf.pages) <= 100:
            raise ValueError("对账单页数无效")
        period_start, period_end = _statement_period(pdf.pages[0].extract_text() or "")
        summary_rows: list[list[str | None]] = []
        detail_rows: list[list[str | None]] = []
        summary_totals: list[list[str | None]] = []
        detail_totals: list[list[str | None]] = []
        summary_seen = detail_seen = False
        active_kind: Literal["summary", "detail"] | None = None
        totals_started = False
        repaired = 0
        for page in pdf.pages:
            for table in sorted(page.find_tables(), key=lambda item: item.bbox[1]):
                rows = table.extract()
                for index, row in enumerate(rows):
                    kind = _header_kind(row)
                    if kind == "summary":
                        if detail_seen:
                            raise ValueError("成交表顺序异常")
                        summary_seen = True
                        active_kind = "summary"
                        totals_started = False
                        continue
                    if kind == "detail":
                        if not summary_seen:
                            raise ValueError("成交表顺序异常")
                        detail_seen = True
                        active_kind = "detail"
                        totals_started = False
                        continue
                    if row and _text(row[0]) == "成交日期":
                        raise ValueError("东吴成交表头格式变化")
                    if len(row) not in (11, 14):
                        if active_kind is not None and _is_dated_row(row):
                            raise ValueError("成交表列数与东吴对账单格式不符")
                        continue
                    if not _is_dated_row(row):
                        if active_kind is not None and _is_currency_total(
                            row, active_kind, continuation=totals_started,
                        ):
                            totals_started = True
                            (summary_totals if active_kind == "summary" else detail_totals).append(row)
                            continue
                        if active_kind is not None and any(_text(cell) for cell in row[1:]):
                            raise ValueError("成交行缺少可核实日期或字段")
                        continue
                    if totals_started:
                        raise ValueError("合计行后出现成交明细")
                    if len(row) == 11 and active_kind == "summary":
                        if not _text(row[6]):
                            row = _repair_summary_row(page, table, index, row)
                            repaired += 1
                        summary_rows.append(row)
                    elif len(row) == 14 and active_kind == "detail":
                        detail_rows.append(row)
                    else:
                        raise ValueError("成交表顺序或列数异常")
        if not summary_seen or not detail_seen:
            raise ValueError("东吴成交汇总或交割明细表头缺失")
        if not summary_totals or not detail_totals:
            raise ValueError("东吴成交汇总或交割明细的币种合计行缺失")
        if len(summary_rows) + len(detail_rows) > 50_000:
            raise ValueError("对账单成交行数超出本地核对上限")
        return compare_statement_rows(
            summary_rows, detail_rows,
            period_start=period_start, period_end=period_end,
            repaired_rows=repaired,
            summary_totals=summary_totals, detail_totals=detail_totals,
        )
