import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.research import ResearchPackError, parse_research_pack
from app.research.sample import SAMPLE_FILES, sample_zip


def _zip(files: dict[str, object]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, json.dumps(content, ensure_ascii=False))
    return buffer.getvalue()


def test_fixed_stock_research_pack_round_trip() -> None:
    report = parse_research_pack(sample_zip())
    view = report.to_dict()
    assert view["schema_version"] == "1.0-fixture"
    assert view["source"] == "StockResearchPack synthetic fixture"
    assert view["generated_at"].endswith("+08:00")
    assert view["symbol"] == "DEMO000.SH"
    assert view["quality"] == "PARTIAL"
    sections = {section["key"]: section for section in view["sections"]}
    assert sections["market"]["data"]["data"]["last_close"] == 10.5
    assert sections["fundamental"]["source_file"] == "financial_snapshot.json"
    assert sections["news"]["status"] == "NO_DATA"
    assert sections["sentiment"]["status"] == "SOURCE_ERROR"
    assert sections["bull"]["status"] == "NO_DATA"
    assert sections["bear"]["status"] == "NO_DATA"
    assert "trade_action" not in view
    assert "buy_signal" not in view


def test_missing_and_corrupt_sections_are_not_silently_filled() -> None:
    files = dict(SAMPLE_FILES)
    files.pop("news.json")
    files["market.json"] = "{broken"
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            value = "{broken" if name == "market.json" else json.dumps(content)
            archive.writestr(name, value)
    report = parse_research_pack(buffer.getvalue())
    sections = {section.key: section for section in report.sections}
    assert sections["news"].status == "MISSING"
    assert sections["market"].status == "INVALID"
    assert sections["market"].data is None


def test_reject_invalid_zip_or_missing_manifest() -> None:
    with pytest.raises(ResearchPackError, match="ZIP"):
        parse_research_pack(b"not a zip")
    with pytest.raises(ResearchPackError, match="manifest"):
        parse_research_pack(_zip({"identity.json": {}}))


def test_reject_path_traversal_and_duplicate_members() -> None:
    files = dict(SAMPLE_FILES)
    files["../escape.json"] = {}
    with pytest.raises(ResearchPackError, match="路径"):
        parse_research_pack(_zip(files))
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("manifest.json", "{}")
    with pytest.raises(ResearchPackError, match="重复"):
        parse_research_pack(buffer.getvalue())


def test_reject_manifest_without_source_version_or_timezone() -> None:
    files = dict(SAMPLE_FILES)
    manifest = dict(files["manifest.json"])
    manifest["generated_at"] = "2026-10-14T09:00:00"
    files["manifest.json"] = manifest
    with pytest.raises(ResearchPackError, match="时区"):
        parse_research_pack(_zip(files))
    manifest["source"] = ""
    with pytest.raises(ResearchPackError, match="来源"):
        parse_research_pack(_zip(files))


def test_explicit_mapping_never_uses_unmapped_alias_fallback() -> None:
    files = dict(SAMPLE_FILES)
    manifest = dict(files["manifest.json"])
    mapping = dict(manifest["files"])
    mapping["news"] = "missing-news.json"
    manifest["files"] = mapping
    files["manifest.json"] = manifest
    report = parse_research_pack(_zip(files))
    assert next(s for s in report.sections if s.key == "news").status == "MISSING"


def test_archive_limit() -> None:
    with pytest.raises(ResearchPackError, match="大小"):
        parse_research_pack(b"x" * (16 * 1024 * 1024 + 1))
