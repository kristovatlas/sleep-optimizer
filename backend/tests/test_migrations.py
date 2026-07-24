"""Tests for the alembic migration chain and init_db stamping (issues #49/#68).

Covers the acceptance criteria from both issues: ``alembic upgrade head``
runs clean against an empty database, a database created by ``init_db()``,
and a legacy unstamped database — and the migrated schema is identical to
what ``Base.metadata.create_all`` produces.
"""

import configparser
import logging
import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from alembic import command
from backend import database
from backend.config import settings
from backend.database import Base
from backend.models import *  # noqa: F403 — register all models on Base

REPO_ROOT = database._ALEMBIC_DIR.parent
ALL_MODEL_TABLES = set(Base.metadata.tables.keys())
HEAD = database._alembic_head()


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(database._ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _stamped_revision(db_path: Path) -> str | None:
    eng = database.create_db_engine(str(db_path))
    try:
        with eng.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        return row[0] if row else None
    except OperationalError:  # no alembic_version table — never stamped
        return None
    finally:
        eng.dispose()


def _drop_version_table(db_path: Path) -> None:
    """Turn a migrated DB into a legacy never-stamped one (pre-#49 install)."""
    eng = database.create_db_engine(str(db_path))
    try:
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE alembic_version"))
    finally:
        eng.dispose()


@pytest.fixture(name="tmp_db")
def tmp_db_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Point the app engine and settings at a throwaway file database."""
    db_path = tmp_path / "somnus-test.db"
    eng = database.create_db_engine(str(db_path))
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(settings, "db_path", db_path)
    yield db_path
    eng.dispose()


# --- #68: the migration chain must build a database from scratch ---


def test_upgrade_head_on_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    command.upgrade(_cfg(db_path), "head")

    eng = database.create_db_engine(str(db_path))
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    assert tables == ALL_MODEL_TABLES | {"alembic_version"}
    assert _stamped_revision(db_path) == HEAD


def test_migrated_schema_matches_create_all(tmp_path: Path) -> None:
    """000→001→002 must land on exactly the schema the app creates itself."""
    db_path = tmp_path / "migrated.db"
    command.upgrade(_cfg(db_path), "head")

    eng = database.create_db_engine(str(db_path))
    try:
        with eng.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "include_name": lambda name, type_, _: (
                        not (type_ == "table" and name == "alembic_version")
                    )
                },
            )
            diffs = compare_metadata(ctx, Base.metadata)
    finally:
        eng.dispose()

    assert diffs == [], f"migrated schema differs from create_all: {diffs}"


def test_alembic_ini_parses_without_interpolation_error() -> None:
    """Regression for #68: a %(...)s value in alembic.ini crashes configparser."""
    parser = configparser.ConfigParser()
    parser.read(REPO_ROOT / "alembic.ini")
    section = dict(parser["alembic"])  # raises InterpolationError on regression
    assert "sqlalchemy.url" not in section  # env.py owns the URL


def test_cli_upgrade_head_honors_somnus_db_path(tmp_path: Path) -> None:
    """The documented release check: SOMNUS_DB_PATH=<db> alembic upgrade head."""
    db_path = tmp_path / "cli.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "SOMNUS_DB_PATH": str(db_path)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert db_path.exists()
    assert _stamped_revision(db_path) == HEAD


# --- #49: init_db stamps fresh and legacy databases ---


def test_init_db_fresh_creates_schema_and_stamps_head(tmp_db: Path) -> None:
    database.init_db()

    tables = set(inspect(database.engine).get_table_names())
    assert tables >= ALL_MODEL_TABLES
    assert _stamped_revision(tmp_db) == HEAD


def test_upgrade_is_noop_on_init_db_database(tmp_db: Path) -> None:
    """The original #49 failure: make migrate crashed on every app-created DB."""
    database.init_db()
    command.upgrade(_cfg(tmp_db), "head")  # must not raise (duplicate column)
    assert _stamped_revision(tmp_db) == HEAD


def test_init_db_repair_stamps_unstamped_current_schema(tmp_db: Path) -> None:
    """Pre-fix installs: full current schema, no alembic_version row."""
    Base.metadata.create_all(bind=database.engine)
    assert _stamped_revision(tmp_db) is None

    database.init_db()
    assert _stamped_revision(tmp_db) == HEAD
    command.upgrade(_cfg(tmp_db), "head")  # and the upgrade path now works


@pytest.mark.parametrize(
    ("schema_revision", "expected_stamp"),
    [("000_baseline", "000_baseline"), ("001", "001")],
)
def test_init_db_stamps_legacy_schema_at_matching_revision(
    tmp_db: Path,
    caplog: pytest.LogCaptureFixture,
    schema_revision: str,
    expected_stamp: str,
) -> None:
    """An old unstamped DB is stamped where its schema actually is, then
    warned to migrate — never silently half-patched by create_all."""
    command.upgrade(_cfg(tmp_db), schema_revision)
    _drop_version_table(tmp_db)

    with caplog.at_level(logging.WARNING, logger="backend.database"):
        database.init_db()

    assert _stamped_revision(tmp_db) == expected_stamp
    assert any("make migrate" in rec.message for rec in caplog.records)
    tables = set(inspect(database.engine).get_table_names())
    assert "experiments" not in tables  # init_db did not create_all-patch it

    command.upgrade(_cfg(tmp_db), "head")  # the guided fix completes cleanly
    assert _stamped_revision(tmp_db) == HEAD


def test_init_db_warns_but_does_not_touch_stamped_behind_head_db(
    tmp_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command.upgrade(_cfg(tmp_db), "001")

    with caplog.at_level(logging.WARNING, logger="backend.database"):
        database.init_db()

    assert _stamped_revision(tmp_db) == "001"
    assert any("make migrate" in rec.message for rec in caplog.records)
    assert "experiments" not in set(inspect(database.engine).get_table_names())


def test_init_db_quiet_on_stamped_current_db(
    tmp_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database.init_db()
    with caplog.at_level(logging.WARNING, logger="backend.database"):
        database.init_db()
    assert caplog.records == []


def test_init_db_rejects_unrecognizable_database(tmp_db: Path) -> None:
    """Tables present, but no user_settings and no stamp: not ours — refuse
    loudly instead of crashing with NoSuchTableError or adopting a foreign file."""
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TABLE foreign_stuff (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="not a recognizable Somnus database"):
        database.init_db()


def test_init_db_repairs_hybrid_legacy_schema(
    tmp_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Pre-001 DB later booted under 002-era code: old create_all added the
    experiments TABLE but never the last_oura_sync COLUMN. No revision matches
    that shape — init_db must apply 001's delta itself, then stamp 002."""
    command.upgrade(_cfg(tmp_db), "000_baseline")
    _drop_version_table(tmp_db)
    Base.metadata.tables["experiments"].create(bind=database.engine)

    with caplog.at_level(logging.WARNING, logger="backend.database"):
        database.init_db()

    assert _stamped_revision(tmp_db) == "002"
    columns = {c["name"] for c in inspect(database.engine).get_columns("user_settings")}
    assert "last_oura_sync" in columns
    assert any("legacy hybrid" in rec.message for rec in caplog.records)
    command.upgrade(_cfg(tmp_db), "head")  # completes cleanly from the repair
    assert _stamped_revision(tmp_db) == HEAD


def test_init_db_treats_empty_version_table_as_unstamped(tmp_db: Path) -> None:
    """An alembic_version table with zero rows means unstamped, not 'behind
    head' — telling the user to run make migrate would dead-end (upgrade from
    base collides with the existing tables)."""
    command.upgrade(_cfg(tmp_db), "head")
    with database.engine.begin() as conn:
        conn.execute(text("DELETE FROM alembic_version"))

    database.init_db()
    assert _stamped_revision(tmp_db) == HEAD


def test_init_db_bootstraps_version_table_only_database(tmp_db: Path) -> None:
    """A file holding only alembic_version (e.g. a stray `alembic stamp`) has
    no model tables — treat it as fresh, not as a healthy stamped-at-head DB
    that would 500 on every request."""
    database._stamp_version(HEAD)
    assert set(inspect(database.engine).get_table_names()) == {"alembic_version"}

    database.init_db()
    tables = set(inspect(database.engine).get_table_names())
    assert tables >= ALL_MODEL_TABLES
    assert _stamped_revision(tmp_db) == HEAD


def test_bare_init_db_subprocess_creates_full_schema(tmp_path: Path) -> None:
    """The `make migrate` pre-step imports ONLY backend.database. Without
    init_db registering the models itself, a fresh DB would be stamped at
    head with zero tables (Codex P2 on PR #87)."""
    db_path = tmp_path / "bare.db"
    result = subprocess.run(
        [sys.executable, "-c", "from backend.database import init_db; init_db()"],
        cwd=REPO_ROOT,
        env={**os.environ, "SOMNUS_DB_PATH": str(db_path)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    eng = database.create_db_engine(str(db_path))
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    assert tables >= ALL_MODEL_TABLES
    assert _stamped_revision(db_path) == HEAD


def test_migration_003_adds_redlight_distance(tmp_path: Path) -> None:
    """#60: the 003 migration adds red_light_entries.distance_inches, and
    the chain still reaches head cleanly (first real post-baseline delta)."""
    db_path = tmp_path / "m003.db"
    command.upgrade(_cfg(db_path), "head")
    eng = database.create_db_engine(str(db_path))
    try:
        cols = {c["name"] for c in inspect(eng).get_columns("red_light_entries")}
    finally:
        eng.dispose()
    assert "distance_inches" in cols


def test_migration_004_adds_section_absences(tmp_path: Path) -> None:
    """#159: the 004 migration creates section_absences (the explicit-absence
    table) with its (date, section_key) unique constraint, and the chain still
    reaches head cleanly. ALL_MODEL_TABLES is derived from the models, so the
    parity tests above also assert migrate-up lands on exactly this table set."""
    db_path = tmp_path / "m004.db"
    command.upgrade(_cfg(db_path), "head")
    eng = database.create_db_engine(str(db_path))
    try:
        insp = inspect(eng)
        assert "section_absences" in set(insp.get_table_names())
        cols = {c["name"] for c in insp.get_columns("section_absences")}
        uniques = {uc["name"] for uc in insp.get_unique_constraints("section_absences")}
    finally:
        eng.dispose()
    assert {"id", "date", "section_key"} <= cols
    assert "uq_section_absence" in uniques
    assert "section_absences" in ALL_MODEL_TABLES  # model registers the table


def test_migration_005_adds_supplement_products_and_fk(tmp_path: Path) -> None:
    """#161 Lane 2: the 005 migration creates the supplement_products library
    table and adds supplement_entries.product_id (nullable FK), and the chain
    still reaches head cleanly. Additive: legacy dose_mg/name columns survive."""
    db_path = tmp_path / "m005.db"
    command.upgrade(_cfg(db_path), "head")
    eng = database.create_db_engine(str(db_path))
    try:
        insp = inspect(eng)
        tables = set(insp.get_table_names())
        product_cols = {c["name"] for c in insp.get_columns("supplement_products")}
        entry_cols = {c["name"] for c in insp.get_columns("supplement_entries")}
        fks = insp.get_foreign_keys("supplement_entries")
    finally:
        eng.dispose()
    assert "supplement_products" in tables
    assert {"id", "name", "brand", "form", "default_dose", "unit", "step", "is_sticky"} <= (
        product_cols
    )
    # Legacy columns preserved; product_id added.
    assert {"name", "dose_mg", "product_id"} <= entry_cols
    assert "supplement_products" in ALL_MODEL_TABLES  # model registers the table
    # The new nullable FK points product_id → supplement_products.id.
    assert any(
        fk["referred_table"] == "supplement_products"
        and fk["constrained_columns"] == ["product_id"]
        for fk in fks
    )


def test_migration_005_downgrade_round_trip(tmp_path: Path) -> None:
    """upgrade head → downgrade 004 → upgrade head must be clean (proves the
    batch-mode add/drop of product_id + the products table both reverse)."""
    db_path = tmp_path / "m005rt.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "004")

    eng = database.create_db_engine(str(db_path))
    try:
        insp = inspect(eng)
        assert "supplement_products" not in set(insp.get_table_names())
        assert "product_id" not in {c["name"] for c in insp.get_columns("supplement_entries")}
    finally:
        eng.dispose()

    command.upgrade(cfg, "head")  # forward again, cleanly
    assert _stamped_revision(db_path) == HEAD
