"""Evidence-backed, non-executing candidate watchlist for Structure Swing v1.

All market/risk classifications and C/A/B hints are *inputs*, not inferred from
candles. A hint is never a confirmed Setup or an instruction to trade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable


class Board(StrEnum):
    MAIN = "MAIN"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class Liquidity(StrEnum):
    GOOD = "GOOD"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class Size(StrEnum):
    LARGE = "LARGE"
    MID = "MID"
    SMALL = "SMALL"
    UNKNOWN = "UNKNOWN"


class ListingAge(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    NEW = "NEW"
    UNKNOWN = "UNKNOWN"


class SetupHint(StrEnum):
    C = "C"
    A = "A"
    B = "B"


class RiskCategory(StrEnum):
    ST = "ST"
    DELISTING = "DELISTING"
    INVESTIGATION = "INVESTIGATION"
    FINANCIAL_FRAUD = "FINANCIAL_FRAUD"
    NONSTANDARD_AUDIT = "NONSTANDARD_AUDIT"
    SEVERE_DEBT = "SEVERE_DEBT"
    GOING_CONCERN = "GOING_CONCERN"
    EARNINGS_DECLINE = "EARNINGS_DECLINE"
    HIGH_PLEDGE = "HIGH_PLEDGE"
    MATERIAL_LITIGATION = "MATERIAL_LITIGATION"


class RiskStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    REPORTED = "REPORTED"
    UNKNOWN = "UNKNOWN"


class CandidateStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EXCLUDED = "EXCLUDED"


RED_LINES = frozenset({
    RiskCategory.ST,
    RiskCategory.DELISTING,
    RiskCategory.INVESTIGATION,
    RiskCategory.FINANCIAL_FRAUD,
    RiskCategory.NONSTANDARD_AUDIT,
    RiskCategory.SEVERE_DEBT,
    RiskCategory.GOING_CONCERN,
})
_HINT_RANK = {SetupHint.C: 0, SetupHint.A: 1, SetupHint.B: 2, None: 3}
_STATUS_RANK = {
    CandidateStatus.CANDIDATE: 0,
    CandidateStatus.REVIEW_REQUIRED: 1,
    CandidateStatus.EXCLUDED: 2,
}


@dataclass(frozen=True, slots=True)
class Evidence:
    field: str
    value: str
    source: str
    reference: str
    observed_at: str

    def __post_init__(self) -> None:
        if not all((self.field.strip(), self.value.strip(), self.source.strip(),
                    self.reference.strip(), self.observed_at.strip())):
            raise ValueError("证据字段、值、来源、引用和时间均不能为空")
        try:
            timestamp = datetime.fromisoformat(self.observed_at)
        except ValueError as exc:
            raise ValueError("证据时间必须为 ISO-8601") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("证据时间必须包含时区")


@dataclass(frozen=True, slots=True)
class RiskFact:
    category: RiskCategory
    status: RiskStatus
    evidence: Evidence

    def __post_init__(self) -> None:
        if self.evidence.field != f"risk:{self.category.value}":
            raise ValueError("风险证据字段与风险类别不一致")
        if self.evidence.value != self.status.value:
            raise ValueError("风险证据状态与风险事实不一致")


@dataclass(frozen=True, slots=True)
class CandidateInput:
    symbol: str
    name: str
    board: Board
    liquidity: Liquidity
    size: Size
    listing_age: ListingAge
    setup_hint: SetupHint | None
    evidence: tuple[Evidence, ...]
    risk_facts: tuple[RiskFact, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.name.strip():
            raise ValueError("候选证券代码和名称不能为空")
        fields = {
            "board": self.board.value,
            "liquidity": self.liquidity.value,
            "size": self.size.value,
            "listing_age": self.listing_age.value,
        }
        if self.setup_hint is not None:
            fields["setup_hint"] = self.setup_hint.value
        for field, value in fields.items():
            matches = [item for item in self.evidence if item.field == field]
            if len(matches) != 1 or matches[0].value != value:
                raise ValueError(f"候选字段 {field} 必须有唯一且一致的可追踪证据")
        if self.setup_hint is None and any(e.field == "setup_hint" for e in self.evidence):
            raise ValueError("未提供候选类别时不得伪造 Setup 证据")
        if len({r.category for r in self.risk_facts}) != len(self.risk_facts):
            raise ValueError("同一风险类别不能重复提供冲突状态")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    symbol: str
    name: str
    status: CandidateStatus
    setup_priority_hint: SetupHint | None
    setup_confirmed: bool
    reasons: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    risk_facts: tuple[RiskFact, ...]

    def to_dict(self) -> dict[str, object]:
        """Explicit display-only projection; no entry/exit/position fields."""
        return asdict(self)


def assess_candidate(candidate: CandidateInput) -> CandidateAssessment:
    """Classify supplied facts only; never infer structure, Setup or trade actions."""
    reasons: list[str] = []
    excluded = False
    review = False

    if candidate.board is Board.MAIN:
        reasons.append("主板偏好：有来源证据")
    else:
        reasons.append("非主板或板块未知：偏好降低，不自动排除")
    if candidate.size in (Size.LARGE, Size.MID):
        reasons.append("大中盘偏好：有来源证据")
    else:
        reasons.append("小盘或市值档位未知：偏好降低，不自动排除")

    if candidate.liquidity is Liquidity.GOOD:
        reasons.append("流动性标记良好：有来源证据")
    elif candidate.liquidity is Liquidity.LOW:
        excluded = True
        reasons.append("低流动性：排除候选")
    else:
        review = True
        reasons.append("流动性未知：须核实，不进入可用候选池")

    if candidate.listing_age is ListingAge.NEW:
        excluded = True
        reasons.append("次新股：主动回避")
    elif candidate.listing_age is ListingAge.UNKNOWN:
        review = True
        reasons.append("上市时间分类未知：须核实")

    for risk in candidate.risk_facts:
        if risk.category in RED_LINES:
            if risk.status is RiskStatus.CONFIRMED:
                excluded = True
                reasons.append(f"已确认重大风险 {risk.category.value}：排除")
            else:
                review = True
                reasons.append(f"重大风险 {risk.category.value} 尚未核实：人工复核")
        elif risk.category is RiskCategory.EARNINGS_DECLINE:
            reasons.append("普通业绩下滑：降低观察优先级，不机械排除")
        else:
            reasons.append(f"风险事实 {risk.category.value}：保留证据供人工复核")
            if risk.status is not RiskStatus.CONFIRMED:
                review = True

    if candidate.setup_hint is not None:
        reasons.append(f"{candidate.setup_hint.value} 类仅为外部候选标签，Setup 未确认")
    else:
        reasons.append("未提供 C/A/B 候选标签，等待用户判断结构")

    status = (CandidateStatus.EXCLUDED if excluded else
              CandidateStatus.REVIEW_REQUIRED if review else CandidateStatus.CANDIDATE)
    return CandidateAssessment(
        symbol=candidate.symbol,
        name=candidate.name,
        status=status,
        setup_priority_hint=candidate.setup_hint,
        setup_confirmed=False,
        reasons=tuple(reasons),
        evidence=candidate.evidence,
        risk_facts=candidate.risk_facts,
    )


def screen_candidates(items: Iterable[CandidateInput]) -> tuple[CandidateAssessment, ...]:
    """Stable watchlist ordering: admissibility, C > A > B, then factual preferences."""
    assessments: list[CandidateAssessment] = []
    seen: set[str] = set()
    items_cache = list(items)
    for item in items_cache:
        if item.symbol in seen:
            raise ValueError("同一证券代码在候选批次中重复")
        seen.add(item.symbol)
        assessments.append(assess_candidate(item))

    def rank(row: CandidateAssessment) -> tuple[int, int, int, str]:
        source = next(item for item in items_cache if item.symbol == row.symbol)
        preference_penalty = (
            int(source.board is not Board.MAIN)
            + int(source.size not in (Size.LARGE, Size.MID))
            + int(any(r.category is RiskCategory.EARNINGS_DECLINE for r in source.risk_facts))
        )
        return (_STATUS_RANK[row.status], _HINT_RANK[row.setup_priority_hint],
                preference_penalty, row.symbol)

    return tuple(sorted(assessments, key=rank))
