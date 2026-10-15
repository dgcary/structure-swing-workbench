"""M7 candidate risk visibility regression tests using synthetic facts."""

from dataclasses import replace

from app.candidate.engine import screen_candidate
from app.candidate.facts import Evidence, RiskFact
from test_candidate_engine import sample


def test_soft_risk_evidence_is_preserved_without_trade_signal() -> None:
    item = sample()
    evidence = Evidence("fixture", "fixture://m7/soft-risk", "2026-10-15T08:00:00+08:00")
    result = screen_candidate(
        replace(item, risks=item.risks + (RiskFact("EARNINGS_DECLINE", "PRESENT", evidence),))
    )
    assert result.status == "CANDIDATE"
    assert result.risk_facts[-1].evidence == evidence
    assert all("买入指令" not in message for message in result.messages)
