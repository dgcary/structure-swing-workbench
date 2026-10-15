"""Evidence-only candidate screening. C/A/B is a caller-provided review lane, never a detected Setup."""
from dataclasses import asdict, dataclass

from app.candidate.facts import HARD_RISKS, SOFT_RISKS, Evidence, ObservedFact, RiskFact

LANE_ORDER = {"C": 0, "A": 1, "B": 2, None: 3}
STATUS_ORDER = {"CANDIDATE": 0, "REVIEW": 1, "EXCLUDED": 2}


@dataclass(frozen=True, slots=True)
class CandidateInput:
    symbol: str
    name: str
    board: ObservedFact
    liquidity: ObservedFact
    size: ObservedFact
    listing_age: ObservedFact
    risks: tuple[RiskFact, ...]
    review_lane: str | None = None
    review_lane_evidence: Evidence | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.name.strip():
            raise ValueError("证券代码与名称不能为空")
        for fact, values in (
            (self.board, {"MAIN", "OTHER", "UNKNOWN"}),
            (self.liquidity, {"GOOD", "LOW", "UNKNOWN"}),
            (self.size, {"MID_LARGE", "SMALL", "UNKNOWN"}),
            (self.listing_age, {"ESTABLISHED", "NEW", "UNKNOWN"}),
        ):
            if not isinstance(fact, ObservedFact):
                raise TypeError("基础分类必须使用带证据的 ObservedFact")
            if fact.value not in values:
                raise ValueError("基础分类值不合法")
        if self.review_lane not in LANE_ORDER:
            raise ValueError("候选复核通道只能为 C/A/B 或未分类")
        if (self.review_lane is None) != (self.review_lane_evidence is None):
            raise ValueError("复核通道必须有独立证据，且不能自动推断 Setup")
        if self.review_lane_evidence is not None and not isinstance(
            self.review_lane_evidence, Evidence
        ):
            raise TypeError("复核通道证据必须使用 Evidence")
        if not isinstance(self.risks, tuple) or any(
            not isinstance(risk, RiskFact) for risk in self.risks
        ):
            raise TypeError("风险事实必须使用带证据的 RiskFact 元组")
        codes = [risk.code for risk in self.risks]
        if len(codes) != len(set(codes)):
            raise ValueError("同一风险事实不得重复")


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    symbol: str
    name: str
    status: str
    review_lane: str | None
    review_lane_evidence: Evidence | None
    profile_facts: tuple[ObservedFact, ...]
    reasons: tuple[ObservedFact, ...]
    risk_facts: tuple[RiskFact, ...]
    missing_risk_checks: tuple[str, ...]
    messages: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def screen_candidate(item: CandidateInput) -> ScreeningResult:
    """Use only supplied observations; missing red-line checks remain REVIEW."""
    checks = {risk.code: risk for risk in item.risks}
    missing = tuple(sorted(HARD_RISKS - checks.keys()))
    present = sorted(
        code for code in HARD_RISKS if code in checks and checks[code].state == "PRESENT"
    )
    unknown = sorted(
        code for code in HARD_RISKS if code in checks and checks[code].state == "UNKNOWN"
    )
    profile_facts = (item.board, item.liquidity, item.size, item.listing_age)
    reasons: list[ObservedFact] = []
    messages: list[str] = []
    for fact, preferred, label in (
        (item.board, "MAIN", "主板"),
        (item.liquidity, "GOOD", "流动性良好"),
        (item.size, "MID_LARGE", "大中盘"),
        (item.listing_age, "ESTABLISHED", "非次新"),
    ):
        if fact.value == preferred:
            reasons.append(fact)
            messages.append("客观偏好：" + label)

    if item.board.value == "OTHER":
        messages.append("非优选：非主板；保留原始分类证据供人工复核")
    if item.size.value == "SMALL":
        messages.append("非优选：小盘；保留原始分类证据供人工复核")
    if present:
        messages.append("排除：已确认重大风险 " + "、".join(present))
    if item.liquidity.value == "LOW":
        messages.append("排除：低流动性")
    if item.listing_age.value == "NEW":
        messages.append("排除：次新")
    if missing:
        messages.append("待核实：缺少风险检查 " + "、".join(missing))
    if unknown:
        messages.append("待核实：重大风险状态未知 " + "、".join(unknown))
    unknown_profile = any(
        fact.value == "UNKNOWN"
        for fact in (item.board, item.liquidity, item.size, item.listing_age)
    )
    if unknown_profile:
        messages.append("待核实：基础分类存在未知值")

    if present or item.liquidity.value == "LOW" or item.listing_age.value == "NEW":
        status = "EXCLUDED"
    elif missing or unknown or unknown_profile:
        status = "REVIEW"
    else:
        status = "CANDIDATE"
    soft_present = sorted(
        code for code in SOFT_RISKS if code in checks and checks[code].state == "PRESENT"
    )
    soft_unknown = sorted(
        code for code in SOFT_RISKS if code in checks and checks[code].state == "UNKNOWN"
    )
    if soft_present:
        messages.append("提示：非硬排除风险待人工核查 " + "、".join(soft_present))
    if soft_unknown:
        messages.append("提示：非硬排除风险状态未知 " + "、".join(soft_unknown))
    if item.review_lane:
        messages.append("C/A/B 仅为外部提供的候选复核顺序，不代表 Setup 成立")
    else:
        messages.append("未提供复核通道；不自动判断 Setup")
    messages.append("不生成买卖信号；用户负责结构、关键位与最终交易")
    return ScreeningResult(
        symbol=item.symbol,
        name=item.name,
        status=status,
        review_lane=item.review_lane,
        review_lane_evidence=item.review_lane_evidence,
        profile_facts=profile_facts,
        reasons=tuple(reasons),
        risk_facts=item.risks,
        missing_risk_checks=missing,
        messages=tuple(messages),
    )


def screen_candidates(items: tuple[CandidateInput, ...]) -> tuple[ScreeningResult, ...]:
    """Order externally tagged review lanes C>A>B within each risk state."""
    if len({item.symbol for item in items}) != len(items):
        raise ValueError("候选证券代码不得重复")
    results = (screen_candidate(item) for item in items)
    return tuple(sorted(
        results, key=lambda r: (STATUS_ORDER[r.status], LANE_ORDER[r.review_lane], r.symbol)
    ))
