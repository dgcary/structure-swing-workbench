from dataclasses import replace

from app.candidate.engine import screen_candidate
from app.candidate.facts import RiskFact
from test_candidate_engine import E, sample


def test_named_soft_risk_facts() -> None:
    item = sample()
    risks = item.risks + (
        RiskFact("EARNINGS_DECLINE", "PRESENT", E),
        RiskFact("SHARE_PLEDGE", "UNKNOWN", E),
    )
    result = screen_candidate(replace(item, risks=risks))
    assert result.status == "CANDIDATE"
    assert any("EARNINGS_DECLINE" in text for text in result.messages)
    assert any("SHARE_PLEDGE" in text for text in result.messages)
