"""Evidence-backed candidate screening endpoint (display only, no trade signals)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.schemas import CandidateScreenRequest
from app.candidate import present_screening_result
from app.candidate.engine import CandidateInput, screen_candidate, screen_candidates
from app.candidate.facts import Evidence, ObservedFact, RiskFact

router = APIRouter(tags=["candidates"])


def _evidence(item: Any) -> Evidence:
    return Evidence(
        source=item.source, reference=item.reference, observed_at=item.observed_at
    )


def _fact(item: Any) -> ObservedFact:
    return ObservedFact(value=item.value, evidence=_evidence(item.evidence))


def _risk(item: Any) -> RiskFact:
    return RiskFact(code=item.code, state=item.state, evidence=_evidence(item.evidence))


def _input(request: CandidateScreenRequest) -> CandidateInput:
    return CandidateInput(
        symbol=request.symbol,
        name=request.name,
        board=_fact(request.board),
        liquidity=_fact(request.liquidity),
        size=_fact(request.size),
        listing_age=_fact(request.listing_age),
        risks=tuple(_risk(item) for item in request.risks),
        review_lane=request.review_lane,
        review_lane_evidence=(
            _evidence(request.review_lane_evidence) if request.review_lane_evidence else None
        ),
    )


@router.post("/candidates/screen")
def screen(request: CandidateScreenRequest) -> dict:
    try:
        result = screen_candidate(_input(request))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return present_screening_result(result)


@router.post("/candidates/screen-batch")
def screen_batch(requests: list[CandidateScreenRequest]) -> list[dict]:
    try:
        results = screen_candidates(tuple(_input(item) for item in requests))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [present_screening_result(result) for result in results]
