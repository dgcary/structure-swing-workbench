from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    db_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(db_engine, "connect")
    def _enable_foreign_keys(
        dbapi_connection, _connection_record
    ) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(db_engine)
    try:
        yield db_engine
    finally:
        Base.metadata.drop_all(db_engine)
        db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
        db_session.rollback()
