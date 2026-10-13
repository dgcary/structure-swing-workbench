from app.account.imports import parse_number


def test_positive_amount():
    assert parse_number("12", "value") == 12
