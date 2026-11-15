"""Workbench REST API layer."""

from fastapi import APIRouter

from app.api import account, actions, candidates, market, plans

api_router = APIRouter()
api_router.include_router(plans.router)
api_router.include_router(actions.router)
api_router.include_router(account.router)
api_router.include_router(candidates.router)
api_router.include_router(market.router)
