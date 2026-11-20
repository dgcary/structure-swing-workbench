"""LLM-assisted plan drafting: natural language -> structured draft fields.

边界（architecture.md §4.4，不可违反）：
- LLM 只从用户自述文本中**提取**结构化字段（价格、百分比、Setup 类型等），不推断；
- 主观确认字段（reversal_confirmed、structure_invalidated、
  remaining_exit_condition_triggered）**恒为 None**，即使文本声称"已确认"，
  也必须由用户在工作台显式设置；
- 草稿不创建计划、不触发审计；创建（POST /plans）与审计仍走正常流程。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import EntryMode, SetupType, StructureStage, TargetType

SYSTEM_PROMPT = """你是 A 股交易计划结构化助手。把用户的自然语言描述转换为严格的 JSON 对象，字段如下：
{
  "instrument_code": "6位证券代码字符串或null",
  "instrument_name": "证券名称字符串或null",
  "setup_type": "c"|"a"|"b"|null（仅当用户自己说明 Setup 类型时填写）,
  "structure_stage": "early"|"middle"|"late"|null,
  "entry_mode": "single_price"|"price_range"|null（给出价格区间为 price_range，单一价格为 single_price）,
  "initial_entry_price_low": 数字或null（建仓下沿或单一计划价）,
  "initial_entry_price_high": 数字或null（建仓上沿，单一价格时为null）,
  "structure_invalidation_price": 数字或null（结构失效价/止损价）,
  "structure_invalidation_condition": "结构失效条件文字或null",
  "planned_total_position_pct": 数字或null（计划总仓位百分比，如 30 表示 30%）,
  "initial_entry_pct": 数字或null（初始建仓百分比）,
  "confirmation_add_pct": 数字或null（确认加仓百分比）,
  "t_reserve_pct": 数字或null（T仓/机动仓百分比）,
  "confirmation_trigger_price": 数字或null（确认加仓触发价）,
  "first_target_price": 数字或null（第一目标价）,
  "first_target_type": "prior_high"|"range_top"|"major_resistance"|"other"|null,
  "first_target_reduce_pct": 数字或null（第一目标减仓百分比）,
  "user_note": "补充说明或null"
}
规则：
- 只输出 JSON 对象本身，不要输出任何解释文字、markdown 代码块或注释；
- 用户没有提到的字段一律填 null，不要猜测；
- 金额、价格、百分比用数字，不要带单位或文字；
- 不要编造用户没有提供的数字。"""


class LlmError(ValueError):
    """LLM 草稿生成失败。"""


@dataclass(frozen=True, slots=True)
class LlmPlanDraft:
    instrument_code: str | None
    instrument_name: str | None
    version_data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_code": self.instrument_code,
            "instrument_name": self.instrument_name,
            "version_data": self.version_data,
            "warnings": list(self.warnings),
        }


def draft_plan_from_text(
    text: str, complete: Callable[[str, str], str]
) -> LlmPlanDraft:
    """调用 LLM 并把返回的 JSON 收敛为安全的草稿字段。"""

    if not text.strip():
        raise LlmError("计划描述不能为空")
    raw = complete(SYSTEM_PROMPT, text)
    data = _extract_json(raw)
    return _build_draft(data)


def _extract_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise LlmError("LLM 返回内容不包含 JSON 对象")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmError("LLM 返回的 JSON 无法解析") from exc
    if not isinstance(data, dict):
        raise LlmError("LLM 返回的 JSON 不是对象")
    return data


def _decimal(value: Any, label: str, warnings: list[str]) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        warnings.append(f"{label}不是有效数字，已忽略：{value!r}")
        return None
    if not number.is_finite() or number <= 0:
        warnings.append(f"{label}必须为正数，已忽略：{value!r}")
        return None
    return number


def _enum(enum_cls: type, value: Any, label: str, warnings: list[str]) -> Any | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    for member in enum_cls:
        if member.value == text:
            return member
    warnings.append(f"{label}取值不合法，已忽略：{value!r}")
    return None


def _text(value: Any, label: str, warnings: list[str]) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        warnings.append(f"{label}为空，已忽略")
        return None
    return cleaned


def _stock_code(value: Any, warnings: list[str]) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    digits = raw.split(".")[0] if raw.endswith(".0") else raw
    if digits.isascii() and digits.isdecimal() and 1 <= len(digits) <= 6:
        return digits.zfill(6)
    warnings.append(f"证券代码不合法，已忽略：{raw!r}")
    return None


def _build_draft(data: dict[str, Any]) -> LlmPlanDraft:
    warnings: list[str] = []
    version: dict[str, Any] = {}

    instrument_code = _stock_code(data.get("instrument_code"), warnings)
    instrument_name = _text(data.get("instrument_name"), "证券名称", warnings)

    setup = _enum(SetupType, data.get("setup_type"), "Setup 类型", warnings)
    if setup is not None:
        version["setup_type"] = setup
    stage = _enum(StructureStage, data.get("structure_stage"), "结构阶段", warnings)
    if stage is not None:
        version["structure_stage"] = stage
    mode = _enum(EntryMode, data.get("entry_mode"), "建仓方式", warnings)
    if mode is not None:
        version["entry_mode"] = mode

    entry_low = _decimal(data.get("initial_entry_price_low"), "计划买入下沿", warnings)
    entry_high = _decimal(data.get("initial_entry_price_high"), "计划买入上沿", warnings)
    if entry_low is not None:
        version["initial_entry_price_low"] = entry_low
    if entry_high is not None and entry_low is not None and entry_high > entry_low:
        version["initial_entry_price_high"] = entry_high
    elif entry_high is not None:
        warnings.append("计划买入上沿不高于下沿，已忽略")

    invalidation = _decimal(
        data.get("structure_invalidation_price"), "结构失效价", warnings
    )
    if invalidation is not None:
        version["structure_invalidation_price"] = invalidation
    condition = _text(
        data.get("structure_invalidation_condition"), "结构失效条件", warnings
    )
    if condition is not None:
        version["structure_invalidation_condition"] = condition

    for key, label in (
        ("planned_total_position_pct", "计划总仓位"),
        ("initial_entry_pct", "初始建仓比例"),
        ("confirmation_add_pct", "确认加仓比例"),
        ("t_reserve_pct", "T仓比例"),
        ("confirmation_trigger_price", "确认加仓触发价"),
        ("first_target_price", "第一目标价"),
        ("first_target_reduce_pct", "第一目标减仓比例"),
    ):
        number = _decimal(data.get(key), label, warnings)
        if number is not None:
            version[key] = number

    target_type = _enum(TargetType, data.get("first_target_type"), "第一目标类型", warnings)
    if target_type is not None:
        version["first_target_type"] = target_type

    note = _text(data.get("user_note"), "补充说明", warnings)
    if note is not None:
        version["user_note"] = note

    # 架构边界：主观确认字段永不来自 LLM。
    version.pop("reversal_confirmed", None)
    version.pop("structure_invalidated", None)
    version.pop("remaining_exit_condition_triggered", None)

    return LlmPlanDraft(instrument_code, instrument_name, version, warnings)
