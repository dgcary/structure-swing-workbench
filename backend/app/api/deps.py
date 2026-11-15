"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import build_engine, build_session_factory
from app.market_data.contracts import MarketDataProvider


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    engine = build_engine(get_settings().database_url)
    return build_session_factory(engine)


def get_session() -> Generator[Session, None, None]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_market_provider() -> MarketDataProvider:
    """Resolve the market-data adapter lazily so core modules never import akshare."""

    from app.market_data.akshare_adapter import AKShareProvider

    try:
        return AKShareProvider()
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="行情依赖 akshare 未安装，请在部署环境安装 market 可选依赖后重试",
        ) from exc
