"""Only synthetic statement rows are checked into source control."""

from dataclasses import asdict
from datetime import date
from types import SimpleNamespace

import pdfplumber
import pytest

from app.workbench.dongwu_statement import check_dongwu_statement_pdf, compare_statement_rows

SUMMARY = [
    "20260805", "深A", "人民币", "买入", "000001", "合成标的", "300",
    "-3000.00", "1.00", "0.00", "0.00",
]
DETAIL = [
    ["20260805", "深A", "人民币", "买入", "000001", "合成标的", "100",
     "10.00", "-1000.00", "0.50", "0.00", "0.00", "0.00", "100"],
    ["20260805", "深A", "人民币", "买入", "000001", "合成标的", "200",
     "10.00", "-2000.00", "0.50", "0.00", "0.00", "0.00", "300"],
]


def check(summary=None, detail=None):
    return compare_statement_rows(
        [SUMMARY if summary is None else summary],
        DETAIL if detail is None else detail,
        period_start=date(2026, 8, 5), period_end=date(2026, 11, 2),
        repaired_rows=0,
    )


def test_grouped_detail_matches_summary_without_broker_certification():
    result = check()
    assert result.status == "matched_unverified"
    assert result.summary_row_count == 1
    assert result.detail_row_count == 2
    assert result.mismatched_group_count == 0
    assert result.broker_reconciled is False
    assert result.full_account_verified is False
    assert result.trade_execution_enabled is False
    assert result.execution_ids_available is False
    assert result.execution_times_available is False
    assert "000001" not in str(asdict(result))


@pytest.mark.parametrize("column,replacement", [
    (6, "301"), (7, "-3000.01"), (8, "1.01"), (9, "0.01"), (10, "0.01"),
])
def test_every_summary_amount_and_fee_must_match(column, replacement):
    changed = SUMMARY.copy()
    changed[column] = replacement
    result = check(summary=changed)
    assert result.status == "mismatch"
    assert result.mismatched_group_count == 1
    assert result.broker_reconciled is False


def test_missing_or_extra_summary_group_is_a_mismatch():
    missing = compare_statement_rows(
        [], DETAIL, period_start=date(2026, 8, 5), period_end=date(2026, 11, 2),
        repaired_rows=0,
    )
    assert missing.status == "mismatch"
    assert missing.missing_summary_group_count == 1

    other = SUMMARY.copy()
    other[4] = "000002"
    extra = compare_statement_rows(
        [SUMMARY, other], DETAIL,
        period_start=date(2026, 8, 5), period_end=date(2026, 11, 2),
        repaired_rows=0,
    )
    assert extra.status == "mismatch"
    assert extra.extra_summary_group_count == 1


@pytest.mark.parametrize("changed", [
    ["20260804", *SUMMARY[1:]],
    [*SUMMARY[:6], "NaN", *SUMMARY[7:]],
    [*SUMMARY[:3], "未知", *SUMMARY[4:]],
])
def test_invalid_or_out_of_period_rows_fail_closed(changed):
    with pytest.raises(ValueError):
        check(summary=changed)


SUMMARY_HEADER = [
    "成交日期", "交易 所", "币种", "交易类 别", "证券代 码", "证券名 称",
    "成交数量合 计", "应收金额合 计", "佣金合计", "印花税合 计", "过户费合 计",
]
DETAIL_HEADER = [
    "成交日期", "交易 所", "币种", "交易 类别", "证券 代码", "证券名 称",
    "成交 数量", "成交 价格", "应收金额", "佣金", "印花税", "过户费",
    "其他费用", "股份 余额",
]


class FakeTable:
    def __init__(self, rows, *, partial_row=None):
        self._rows = rows
        self.rows = []
        for index, row in enumerate(rows):
            cells = [(column, index, column + 1, index + 1) for column in range(len(row))]
            if index == partial_row:
                cells[3:] = [None] * (len(cells) - 3)
            self.rows.append(SimpleNamespace(cells=cells))
        self.bbox = (0, 0, len(rows[0]), len(rows))

    def extract(self):
        return self._rows


class FakePage:
    def __init__(self, text, tables, *, recovered=None):
        self._text = text
        self._tables = tables
        self._recovered = recovered

    def extract_text(self):
        return self._text

    def find_tables(self):
        return self._tables

    def crop(self, box):
        value = self._recovered[int(box[0])] if self._recovered is not None else ""
        return SimpleNamespace(extract_text=lambda: value)


class FakePDF:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def test_pdf_recovers_a_pagebreak_row_before_comparing(monkeypatch):
    other_summary = SUMMARY.copy()
    other_summary[4] = "000002"
    other_detail = DETAIL[0].copy()
    other_detail[4] = "000002"
    other_detail[6] = "300"
    other_detail[8] = "-3000.00"
    other_detail[9] = "1.00"
    summary_total = ["合计", None, "人民币", None, None, None, None, "-6000", "2", "0", "0"]
    detail_total = [
        "合计", None, "人民币", None, None, None, None, None,
        "-6000", "2", "0", "0", "0", None,
    ]
    summary_table = FakeTable(
        [SUMMARY_HEADER, [*SUMMARY[:3], *([None] * 8)], other_summary, summary_total],
        partial_row=1,
    )
    detail_table = FakeTable([DETAIL_HEADER, *DETAIL, other_detail, detail_total])
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026 年08月05日-2026年11月02 日", []),
        FakePage("", [summary_table], recovered=SUMMARY),
        FakePage("", [detail_table]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    result = check_dongwu_statement_pdf(b"synthetic PDF bytes")
    assert result.status == "matched_unverified"
    assert result.repaired_summary_rows == 1
    assert result.summary_row_count == 2
    assert result.detail_row_count == 3
    assert result.broker_reconciled is False


def test_pdf_without_expected_statement_headers_fails_closed(monkeypatch):
    pages = [FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", [])]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="表头"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_matching_rows_without_currency_footers_fail_closed(monkeypatch):
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="合计行"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_rejects_changed_fee_header(monkeypatch):
    changed_header = SUMMARY_HEADER.copy()
    changed_header[8], changed_header[9] = changed_header[9], changed_header[8]
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([changed_header, SUMMARY])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="表头"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_rejects_later_changed_trade_header(monkeypatch):
    changed_header = SUMMARY_HEADER.copy()
    changed_header[9] = "未知费用"
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY]), FakeTable([changed_header])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="表头"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_rejects_unreadable_trade_row(monkeypatch):
    damaged = DETAIL[0].copy()
    damaged[0] = "unreadable"
    damaged[3] = "?"
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL, damaged])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="成交行"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_accepts_typed_currency_totals_across_pages(monkeypatch):
    summary_total = ["合计", None, "人民币", None, None, None, None, "-3000", "1", "0", "0"]
    summary_next_total = [None, None, "港币", None, None, None, None, "0", "0", "0", "0"]
    detail_total = [
        "合计", None, "人民币", None, None, None, None, None,
        "-3000", "1", "0", "0", "0", None,
    ]
    detail_next_total = [
        None, None, "港币", None, None, None, None, None,
        "0", "0", "0", "0", "0", None,
    ]
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY, summary_total])]),
        FakePage("", [FakeTable([summary_next_total]), FakeTable([
            DETAIL_HEADER, *DETAIL, detail_total, detail_next_total,
        ])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    result = check_dongwu_statement_pdf(b"synthetic PDF bytes")
    assert result.status == "matched_unverified"
    assert result.summary_row_count == 1
    assert result.detail_row_count == 2
    assert result.footer_totals_checked is True
    assert result.footer_totals_mismatched_count == 0


def test_pdf_rejects_trade_table_width_change_after_header(monkeypatch):
    wider_row = [*SUMMARY, "unexpected"]
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY]), FakeTable([wider_row])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    with pytest.raises(ValueError, match="列数"):
        check_dongwu_statement_pdf(b"synthetic PDF bytes")


def test_pdf_footer_total_mismatch_downgrades_internal_match(monkeypatch):
    wrong_total = ["合计", None, "人民币", None, None, None, None, "-2999", "1", "0", "0"]
    detail_total = [
        "合计", None, "人民币", None, None, None, None, None,
        "-3000", "1", "0", "0", "0", None,
    ]
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY, wrong_total])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL, detail_total])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    result = check_dongwu_statement_pdf(b"synthetic PDF bytes")
    assert result.status == "mismatch"
    assert result.footer_totals_checked is True
    assert result.footer_totals_mismatched_count == 1


def test_pdf_detail_other_fee_total_mismatch_is_detected(monkeypatch):
    summary_total = ["合计", None, "人民币", None, None, None, None, "-3000", "1", "0", "0"]
    wrong_detail_total = [
        "合计", None, "人民币", None, None, None, None, None,
        "-3000", "1", "0", "0", "0.01", None,
    ]
    pages = [
        FakePage("东吴证券对账单\n账单周期：2026年08月05日-2026年11月02日", []),
        FakePage("", [FakeTable([SUMMARY_HEADER, SUMMARY, summary_total])]),
        FakePage("", [FakeTable([DETAIL_HEADER, *DETAIL, wrong_detail_total])]),
    ]
    monkeypatch.setattr(pdfplumber, "open", lambda _: FakePDF(pages))
    result = check_dongwu_statement_pdf(b"synthetic PDF bytes")
    assert result.status == "mismatch"
    assert result.footer_totals_mismatched_count == 1
