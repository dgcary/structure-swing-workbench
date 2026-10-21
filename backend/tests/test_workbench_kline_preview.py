from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
header = "time,open,high,low,close,volume\n"


def test_valid_bar_is_read_only():
    result = client.post("/workbench/kline-preview", json={
        "timeframe": "day", "data": header + "2026-10-16,10,11,9,10.5,100\n",
    })
    assert result.status_code == 200
    data = result.json()
    assert data["bar_count"] == 1
    assert data["source"] == "user_uploaded_csv"
    assert data["realtime"] is False
    assert data["setup_detected"] is False
    assert data["trade_execution_enabled"] is False


def test_bad_ohlc_and_nan_are_rejected():
    for row in ("2026-10-16,10,9,8,10,100\n",
                "2026-10-16,NaN,11,9,10,100\n",
                "2026-10-16,10,11,9,10,-1\n"):
        assert client.post("/workbench/kline-preview", json={
            "timeframe": "day", "data": header + row,
        }).status_code == 422


def test_duplicate_timestamp_rejected():
    row = "2026-10-16,10,11,9,10,100\n"
    assert client.post("/workbench/kline-preview", json={
        "timeframe": "day", "data": header + row + row,
    }).status_code == 422


def test_minute_bars_require_timezone():
    response = client.post("/workbench/kline-preview", json={
        "timeframe": "5m",
        "data": header + "2026-10-16T09:35:00,10,11,9,10,100\n",
    })
    assert response.status_code == 422

def test_minute_bars_compare_actual_instant_not_offset_text():
    valid = header + (
        "2026-10-16T09:35:00+08:00,10,11,9,10,1\n"
        "2026-10-16T09:30:00+07:00,10,11,9,10,1\n"
    )
    assert client.post("/workbench/kline-preview", json={
        "timeframe": "5m", "data": valid,
    }).status_code == 200
    invalid = header + (
        "2026-10-16T09:35:00+07:00,10,11,9,10,1\n"
        "2026-10-16T09:40:00+08:00,10,11,9,10,1\n"
    )
    assert client.post("/workbench/kline-preview", json={
        "timeframe": "5m", "data": invalid,
    }).status_code == 422


def test_empty_csv_and_invalid_headers_rejected():
    for data in ("time,open,high,low,close,volume\n",
                 "date,open,high,low,close,volume\n2026-10-16,10,11,9,10,1\n"):
        assert client.post("/workbench/kline-preview", json={
            "timeframe": "day", "data": data,
        }).status_code == 422


def test_unclosed_quoted_csv_field_is_rejected():
    # A permissive CSV parser treats this malformed quoted volume as "100".
    # It must not be displayed as a verified historical bar.
    malformed = header + '2026-10-16,10,11,9,10,"100\n'
    response = client.post("/workbench/kline-preview", json={
        "timeframe": "day", "data": malformed,
    })
    assert response.status_code == 422



def test_noncanonical_but_parseable_iso_timestamps_are_rejected():
    # datetime/date.fromisoformat accepts ISO week dates and alternative
    # separators, but the frontend contract requires calendar-date ISO.
    for timeframe, stamp in (
        ("day", "2026-W43-3"),
        ("5m", "2026-W43-3T09:30:00+08:00"),
        ("5m", "2026-10-21 09:30:00+08:00"),
        ("15m", "2026-10-21T09:30+08:00"),
    ):
        response = client.post("/workbench/kline-preview", json={
            "timeframe": timeframe,
            "data": header + f"{stamp},10,11,9,10,100\n",
        })
        assert response.status_code == 422, (timeframe, stamp, response.json())


def test_canonical_minute_timestamp_with_zulu_timezone_is_accepted():
    response = client.post("/workbench/kline-preview", json={
        "timeframe": "5m",
        "data": header + "2026-10-21T01:30:00Z,10,11,9,10,100\n",
    })
    assert response.status_code == 200
    assert response.json()["bars"][0]["time"] == "2026-10-21T01:30:00+00:00"


def test_utf8_bom_header_is_accepted_without_changing_csv_contract():
    response = client.post("/workbench/kline-preview", json={
        "timeframe": "day",
        "data": "\ufeff" + header + "2026-10-16,10,11,9,10,100\n",
    })
    assert response.status_code == 200
    assert response.json()["bar_count"] == 1
    assert response.json()["source"] == "user_uploaded_csv"
