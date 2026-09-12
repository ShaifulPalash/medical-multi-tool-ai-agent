"""
Unit tests for tools/sql_safety.py. No API keys, no network — pure logic
tests against a real, throwaway SQLite file, safe to run in CI on every push.
"""

import os
import sqlite3
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from tools.sql_safety import (
    DEFAULT_ROW_LIMIT,
    UnsafeSQLError,
    get_table_schema,
    run_read_only_query,
    validate_select_only,
)


@pytest.fixture()
def sample_db(tmp_path):
    db_path = tmp_path / "sample_diabetes.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE diabetes (glucose REAL, bmi REAL, outcome INTEGER)")
    conn.executemany(
        "INSERT INTO diabetes VALUES (?, ?, ?)",
        [(148, 33.6, 1), (85, 26.6, 0), (183, 23.3, 1), (None, 28.1, 0)],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_plain_select_is_allowed():
    sql = validate_select_only("SELECT * FROM diabetes WHERE outcome = 1")
    assert sql.upper().startswith("SELECT")


def test_limit_is_auto_appended_when_missing():
    sql = validate_select_only("SELECT * FROM diabetes")
    assert f"LIMIT {DEFAULT_ROW_LIMIT}" in sql


def test_existing_limit_is_preserved_not_duplicated():
    sql = validate_select_only("SELECT * FROM diabetes LIMIT 5")
    assert sql.count("LIMIT") == 1


@pytest.mark.parametrize(
    "bad_sql",
    [
        "DROP TABLE diabetes",
        "DELETE FROM diabetes",
        "UPDATE diabetes SET outcome = 0",
        "INSERT INTO diabetes VALUES (1, 2, 3)",
        "SELECT * FROM diabetes; DROP TABLE diabetes",
        "ATTACH DATABASE 'evil.db' AS evil",
        "PRAGMA table_info(diabetes)",
    ],
)
def test_unsafe_sql_is_rejected(bad_sql):
    with pytest.raises(UnsafeSQLError):
        validate_select_only(bad_sql)


def test_run_read_only_query_returns_expected_rows(sample_db):
    columns, rows = run_read_only_query(sample_db, "SELECT glucose FROM diabetes WHERE outcome = 1")
    assert columns == ["glucose"]
    assert rows == [(148,), (183,)]


def test_avg_ignores_null_glucose_values(sample_db):
    # This is the exact behavior db_tools.py's prompt relies on: AVG()
    # automatically skips NULLs (our zero-as-missing cleaning converts
    # impossible 0 readings to NULL), so a naive AVG() over glucose should
    # NOT be dragged down by any missing-data placeholder.
    columns, rows = run_read_only_query(sample_db, "SELECT AVG(glucose) FROM diabetes")
    avg = rows[0][0]
    # Average of 148, 85, 183 (NULL excluded) = 138.67, NOT diluted by a
    # phantom 0/NULL row.
    assert abs(avg - 138.6666) < 0.01


def test_run_read_only_query_blocks_write_attempt(sample_db):
    with pytest.raises(UnsafeSQLError):
        run_read_only_query(sample_db, "DELETE FROM diabetes")
    conn = sqlite3.connect(sample_db)
    count = conn.execute("SELECT COUNT(*) FROM diabetes").fetchone()[0]
    conn.close()
    assert count == 4


def test_db_level_readonly_blocks_writes_even_bypassing_validator(sample_db):
    uri = f"file:{sample_db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM diabetes")
    conn.close()


def test_get_table_schema_returns_create_statement(sample_db):
    schema = get_table_schema(sample_db, "diabetes")
    assert "CREATE TABLE diabetes" in schema
    assert "glucose" in schema


def test_get_table_schema_returns_empty_for_missing_table(sample_db):
    assert get_table_schema(sample_db, "does_not_exist") == ""
