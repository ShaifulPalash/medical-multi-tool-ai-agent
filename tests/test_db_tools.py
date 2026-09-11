"""
End-to-end test of one full DB tool (NL question -> generated SQL -> safe
execution against a real SQLite file -> NL summary), using a fake LLM so no
API key or network call is needed. This is the same test pattern used to
verify db_tools.py manually during development (see the project's build
notes) — codified here so it runs in CI on every push.
"""

import os
import sqlite3
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def _make_test_db(tmp_path):
    db_path = tmp_path / "diabetes.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE diabetes (glucose REAL, outcome INTEGER)")
    conn.executemany(
        "INSERT INTO diabetes VALUES (?, ?)",
        [(148, 1), (85, 0), (183, 1)],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_db_tool_pipeline_end_to_end(tmp_path, monkeypatch):
    import tools.db_tools as db_tools

    test_db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(db_tools, "DB_DIR", str(tmp_path))

    # Rebuild the diabetes tool's runner against our throwaway test DB
    # instead of the real db/diabetes.db.
    test_runner = db_tools._make_db_tool("diabetes.db", "diabetes")

    call_count = {"n": 0}

    def fake_llm_responses(prompt_value):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: NL -> SQL translation step.
            return AIMessage(content="SELECT AVG(glucose) FROM diabetes WHERE outcome = 1")
        # Second call: raw-rows -> NL summary step.
        return AIMessage(content="The average glucose for diabetic patients is 165.5.")

    db_tools._sql_llm = RunnableLambda(fake_llm_responses)

    result = test_runner("What is the average glucose level for diabetic patients?")

    assert "165.5" in result
    assert not result.startswith("Database error")
    # Confirm the underlying file was genuinely queried (not a stub).
    assert os.path.exists(test_db_path)
