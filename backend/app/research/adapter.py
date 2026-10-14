"""Read-only, provider-neutral StockResearchPack ZIP projection.

No TradingAgents imports, network calls, trade decisions, or execution side effects.
"""
from __future__ import annotations

import json
import stat
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_MEMBER_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 80
STATUSES = frozenset({"OK", "NO_DATA", "SOURCE_ERROR", "MISSING", "INVALID"})
SECTION_FILES = (
    ("market", "市场", ("market.json",)),
    ("technical", "技术数据", ("technical.json",)),
    ("fundamental", "基本面", ("financial_snapshot.json", "fundamental.json")),
    ("news", "新闻", ("news.json",)),
    ("sentiment", "情绪", ("sentiment.json",)),
    ("macro", "宏观", ("macro.json",)),
    ("bull", "多方研究", ("bull_research.json", "bull.json")),
    ("bear", "空方研究", ("bear_research.json", "bear.json")),
    ("evidence", "证据", ("evidence.json",)),
    ("data_quality", "数据质量", ("data_quality.json",)),
)


class ResearchPackError(ValueError):
    """The ZIP or its mandatory manifest cannot be safely interpreted."""


@dataclass(frozen=True, slots=True)
class ResearchSection:
    key: str
    title: str
    status: str
    source_file: str | None
    data: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchReport:
    schema_version: str
    generated_at: str
    source: str
    symbol: str | None
    name: str | None
    quality: str
    sections: tuple[ResearchSection, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ResearchPackError("研究包文件路径不合法")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("..", ".") for part in value.split("/")):
        raise ResearchPackError("研究包包含不安全路径")
    return value


def _read_json(archive: ZipFile, path: str) -> Any:
    info = archive.getinfo(path)
    if info.file_size > MAX_MEMBER_BYTES:
        raise ResearchPackError("研究包单个文件超出大小限制")
    return json.loads(archive.read(info).decode("utf-8"))


def _file_for(
    files: dict[str, Any], key: str, aliases: tuple[str, ...], members: set[str]
) -> str | None:
    candidate = files.get(key)
    if candidate is not None:
        path = _safe_path(candidate)
        return path if path in members else None
    return next((path for path in aliases if path in members), None)


def parse_research_pack(data: bytes) -> ResearchReport:
    """Project a bounded ZIP into display-only research facts and explicit quality states."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ResearchPackError("研究包压缩文件超出大小限制")
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise ResearchPackError("研究包文件数量超出限制")
            members: set[str] = set()
            total = 0
            for info in infos:
                name = _safe_path(info.filename)
                if name in members:
                    raise ResearchPackError("研究包存在重复路径")
                members.add(name)
                total += info.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ResearchPackError("研究包解压大小超出限制")
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ResearchPackError("研究包不允许符号链接")
            if "manifest.json" not in members:
                raise ResearchPackError("研究包缺少 manifest.json")
            try:
                manifest = _read_json(archive, "manifest.json")
            except (ValueError, UnicodeError) as exc:
                raise ResearchPackError("manifest.json 不是有效 JSON") from exc
            if not isinstance(manifest, dict):
                raise ResearchPackError("manifest.json 必须是对象")
            version = manifest.get("schema_version")
            source = manifest.get("source")
            generated_at = manifest.get("generated_at")
            if not all(isinstance(v, str) and v.strip() for v in (version, source, generated_at)):
                raise ResearchPackError("manifest 缺少版本、来源或研究时间")
            try:
                parsed_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ResearchPackError("研究时间不是 ISO-8601 格式") from exc
            if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
                raise ResearchPackError("研究时间必须包含时区")
            files = manifest.get("files", {})
            if not isinstance(files, dict):
                raise ResearchPackError("manifest.files 必须是对象")
            identity_path = _file_for(files, "identity", ("identity.json",), members)
            identity: dict[str, Any] = {}
            if identity_path:
                try:
                    raw_identity = _read_json(archive, identity_path)
                    if isinstance(raw_identity, dict):
                        identity = raw_identity
                except (ValueError, UnicodeError):
                    pass
            sections = []
            for key, title, aliases in SECTION_FILES:
                path = _file_for(files, key, aliases, members)
                if path is None:
                    sections.append(ResearchSection(key, title, "MISSING", None))
                    continue
                try:
                    content = _read_json(archive, path)
                    status = content.get("status", "OK") if isinstance(content, dict) else "OK"
                    if not isinstance(status, str) or status not in STATUSES:
                        sections.append(
                            ResearchSection(key, title, "INVALID", path, error="未知数据质量状态")
                        )
                    else:
                        sections.append(ResearchSection(key, title, status, path, content))
                except (ValueError, UnicodeError):
                    sections.append(
                        ResearchSection(key, title, "INVALID", path, error="JSON 内容无效")
                    )
            quality = "OK" if all(s.status == "OK" for s in sections) else "PARTIAL"
            return ResearchReport(
                schema_version=version,
                generated_at=generated_at,
                source=source,
                symbol=identity.get("symbol") if isinstance(identity.get("symbol"), str) else None,
                name=identity.get("name") if isinstance(identity.get("name"), str) else None,
                quality=quality,
                sections=tuple(sections),
            )
    except BadZipFile as exc:
        raise ResearchPackError("不是有效的 ZIP 研究包") from exc
