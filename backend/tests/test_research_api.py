from fastapi.testclient import TestClient

from app.main import app


def test_read_only_sample_endpoint_displays_provenance_and_quality() -> None:
    response = TestClient(app).get("/research/sample")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "StockResearchPack synthetic fixture"
    assert payload["generated_at"].endswith("+08:00")
    assert payload["schema_version"] == "1.0-fixture"
    statuses = {section["key"]: section["status"] for section in payload["sections"]}
    assert statuses["market"] == "OK"
    assert statuses["news"] == "NO_DATA"
    assert statuses["sentiment"] == "SOURCE_ERROR"
    assert "action" not in payload
    assert "order" not in payload
