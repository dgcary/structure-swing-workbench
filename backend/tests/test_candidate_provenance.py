"""Verify the M7 result retains all sourced profile observations."""

from dataclasses import replace

from test_candidate_engine import E, sample

from app.candidate.engine import screen_candidate
from app.candidate.facts import ObservedFact


def test_nonpreferred_profile_keeps_source_links() -> None:
    item = sample()
    result = screen_candidate(replace(
        item, board=ObservedFact("OTHER", E), size=ObservedFact("SMALL", E)
    ))
    assert [fact.value for fact in result.profile_facts] == [
        "OTHER", "GOOD", "SMALL", "ESTABLISHED"
    ]
    assert all(fact.evidence == E for fact in result.profile_facts)
    assert any("非主板" in message for message in result.messages)
    assert any("小盘" in message for message in result.messages)
