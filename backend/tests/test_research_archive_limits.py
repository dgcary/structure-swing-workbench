"""Archive bounds apply to every ZIP entry, including unreferenced files."""
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.research import ResearchPackError, parse_research_pack
from app.research.sample import SAMPLE_FILES


def test_unmapped_member_limit() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, payload in SAMPLE_FILES.items():
            archive.writestr(name, json.dumps(payload))
        archive.writestr("unused.txt", "x" * (4 * 1024 * 1024 + 1))
    with pytest.raises(ResearchPackError, match="单个文件"):
        parse_research_pack(buffer.getvalue())
