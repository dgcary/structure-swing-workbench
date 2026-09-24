from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import Base


def test_alembic_upgrades_empty_database(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "migration-test.db"
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert {
        "trade_plans",
        "trade_plan_versions",
        "trade_actions",
        "execution_fills",
        "account_snapshots",
        "position_snapshots",
        "position_bucket_snapshots",
        "audit_results",
        "manual_overrides",
    }.issubset(set(inspector.get_table_names()))

    plan_columns = {column["name"] for column in inspector.get_columns("trade_plans")}
    version_columns = {
        column["name"] for column in inspector.get_columns("trade_plan_versions")
    }
    action_columns = {column["name"] for column in inspector.get_columns("trade_actions")}

    assert "user_note" in plan_columns
    assert {
        "entry_mode",
        "planned_total_position_amount",
        "remaining_exit_condition_triggered",
    }.issubset(version_columns)
    assert "user_note" not in version_columns
    assert "plan_id" not in action_columns

    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(migration_context, Base.metadata) == []
