"""M5 CSV input rejects malformed batches without partial writes."""

import pytest

from app.account import AccountLedger, import_csv

T = "2026-10-13T10:00:00+08:00"


def test_invalid_second_row_rolls_back_first() -> None:
    book = AccountLedger()
    data = f"symbol,quantity,cost,as_of\nAAA,100,10,{T}\nBBB,-1,11,{T}\n"
    with pytest.raises(ValueError):
        import_csv(book, "holdings", data, batch_id="invalid")
    assert not book.facts
    assert not book.batches


def test_missing_column_and_timezone_rejected() -> None:
    book = AccountLedger()
    with pytest.raises(ValueError, match="缺少字段"):
        import_csv(book, "account", "equity,as_of\n10,2026-10-13\n", batch_id="missing")
    with pytest.raises(ValueError, match="时区"):
        import_csv(
            book, "account",
            "equity,available_cash,as_of\n100,50,2026-10-13T10:00:00\n",
            batch_id="naive",
        )


def test_unterminated_quoted_csv_is_rejected_atomically() -> None:
    book = AccountLedger()
    malformed = (
        "equity,available_cash,as_of\n"
        '"100,50,2026-10-13T10:00:00+08:00\n'
    )
    with pytest.raises(ValueError, match="CSV 格式错误"):
        import_csv(book, "account", malformed, batch_id="bad-quotes")
    assert not book.facts
    assert not book.batches
