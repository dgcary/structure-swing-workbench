"""Fixed, synthetic StockResearchPack ZIP fixture for read-only end-to-end demo."""
from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

SAMPLE_FILES: dict[str, object] = {
    "manifest.json": {
        "schema_version": "1.0-fixture",
        "source": "StockResearchPack synthetic fixture",
        "generated_at": "2026-10-14T09:00:00+08:00",
        "files": {
            "identity": "identity.json",
            "market": "market.json",
            "technical": "technical.json",
            "fundamental": "financial_snapshot.json",
            "news": "news.json",
            "sentiment": "sentiment.json",
            "macro": "macro.json",
            "bull": "bull_research.json",
            "bear": "bear_research.json",
            "evidence": "evidence.json",
            "data_quality": "data_quality.json",
        },
    },
    "identity.json": {"symbol": "DEMO000.SH", "name": "演示证券（虚构）"},
    "market.json": {"status": "OK", "data": {"last_close": 10.5, "currency": "CNY"}},
    "technical.json": {"status": "OK", "data": {"ma5": 10.2, "ma10": 10.1}},
    "financial_snapshot.json": {
        "status": "OK", "data": {"period": "2026-Q2", "revenue": 123456789}
    },
    "news.json": {"status": "NO_DATA", "data": [], "reason": "演示样例无新闻数据"},
    "sentiment.json": {"status": "SOURCE_ERROR", "reason": "演示情绪源不可用"},
    "macro.json": {"status": "OK", "data": {"reference": "演示宏观信息"}},
    "bull_research.json": {"status": "NO_DATA", "reason": "未提供多方研究文本"},
    "bear_research.json": {"status": "NO_DATA", "reason": "未提供空方研究文本"},
    "evidence.json": {"status": "OK", "data": [{"id": "fixture-1", "source": "synthetic"}]},
    "data_quality.json": {
        "status": "OK", "data": {"note": "仅用于适配器和界面演示，不是真实行情"}
    },
}


def sample_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in SAMPLE_FILES.items():
            archive.writestr(name, json.dumps(content, ensure_ascii=False))
    return buffer.getvalue()
