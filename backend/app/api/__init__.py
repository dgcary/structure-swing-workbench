"""Workbench REST API layer."""

from fastapi import APIRouter

from app.api import account, candidates, market, plans

api_router = APIRouter()
api_router.include_router(plans.router)
api_router.include_router(account.router)
api_router.include_router(candidates.router)
api_router.include_router(market.router)
