"""Source-linked objective facts for the M7 candidate review."""
from dataclasses import dataclass
from datetime import datetime

HARD_RISKS = frozenset({
    "ST", "DELISTING", "REGULATORY_INVESTIGATION", "FINANCIAL_FRAUD",
    "QUALIFIED_AUDIT", "SEVERE_DEBT", "GOING_CONCERN",
})
SOFT_RISKS = frozenset({
    "EARNINGS_DECLINE", "SHAREHOLDER_REDUCTION", "SHARE_PLEDGE",
    "MAJOR_LITIGATION", "CASH_FLOW_DETERIORATION", "VALUATION_HIGH",
})


@dataclass(frozen=True, slots=True)
class Evidence:
    source: str
    reference: str
    observed_at: str

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (
            self.source, self.reference, self.observed_at
        )):
            raise ValueError("证据必须提供来源、引用和时间")
        try:
            parsed = datetime.fromisoformat(self.observed_at)
        except ValueError as exc:
            raise ValueError("证据时间必须是 ISO-8601 格式") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("证据时间必须包含时区")


@dataclass(frozen=True, slots=True)
class ObservedFact:
    value: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class RiskFact:
    code: str
    state: str
    evidence: Evidence

    def __post_init__(self) -> None:
        if self.code not in HARD_RISKS | SOFT_RISKS:
            raise ValueError("未知风险事实代码")
        if self.state not in ("PRESENT", "ABSENT", "UNKNOWN"):
            raise ValueError("风险事实状态不合法")
