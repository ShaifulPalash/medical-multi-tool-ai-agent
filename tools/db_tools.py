"""
STEP 4: DB-specific LangChain tools — HeartDiseaseDBTool, CancerDBTool,
DiabetesDBTool.

Each tool follows the same pipeline:

  1. The main agent calls the appropriate database tool with the user's
     plain-English question.

  2. The database tool asks Gemini to generate ONE SQLite SELECT query
     against the table's REAL schema.

  3. tools/sql_safety.py validates that the generated SQL is read-only
     and executes it safely.

  4. The database tool returns the structured query result directly to
     the main agent.

  5. The main agent uses that result to produce the final natural-language
     answer.

IMPORTANT:
We intentionally do NOT call Gemini a second time to summarize the SQL
result inside the database tool.

This reduces unnecessary Gemini API calls while preserving the assignment
functionality.

The tool descriptions (docstrings under @tool) are also used by the main
agent to decide which database tool should handle a question.
"""

import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from tools.sql_safety import (
    UnsafeSQLError,
    get_table_schema,
    run_read_only_query,
)

# ---------------------------------------------------------
# Database directory
# ---------------------------------------------------------

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")


# ---------------------------------------------------------
# Lazy Gemini LLM
# ---------------------------------------------------------
#
# Gemini is created only when a database question actually
# needs SQL generation.
#
# This avoids creating the model during module import, which
# is useful for testing and other environments where the API
# key may not be loaded yet.
# ---------------------------------------------------------

_sql_llm = None


def _get_sql_llm():
    """
    Create the Gemini model only when a database question
    actually needs SQL generation.
    """
    global _sql_llm

    if _sql_llm is None:
        _sql_llm = ChatGoogleGenerativeAI(model=os.getenv("AGENT_MODEL", "gemini-3.6-flash"))

    return _sql_llm


# ---------------------------------------------------------
# Helper: Extract text from Gemini response
# ---------------------------------------------------------
#
# Gemini responses can sometimes contain:
#
#   response.content -> string
#
# or:
#
#   response.content -> list of content blocks
#
# This helper handles both formats.
# ---------------------------------------------------------


def _response_text(response) -> str:
    """
    Extract plain text from a Gemini/LangChain response.
    """
    if isinstance(response.content, str):
        return response.content

    if isinstance(response.content, list):
        text_parts = []

        for block in response.content:
            if isinstance(block, dict):
                text = block.get("text", "")

                if text:
                    text_parts.append(text)

        return "".join(text_parts)

    return str(response.content)


# ---------------------------------------------------------
# Generate SQL
# ---------------------------------------------------------


def _generate_sql(question: str, schema_sql: str, table_name: str) -> str:
    """
    Ask Gemini to convert the user's natural-language question
    into a read-only SQLite SQL query.
    """

    prompt = f"""You are a SQLite expert working with a MEDICAL dataset.

Given this table schema:

{schema_sql}

Write ONE single SQLite SELECT query that answers the user's question below.

Rules:
- Only query the table "{table_name}".
- Return ONLY the raw SQL.
- Do not use markdown code fences.
- Do not provide explanations.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, or any other write statement.
- Only generate a read-only SELECT query.
- Some numeric columns had biologically-impossible 0 values converted to
  NULL during data cleaning (for example blood pressure, glucose, BMI).
- SQLite aggregate functions such as AVG() and SUM() automatically ignore
  NULL values.
- Therefore, you do not need to add extra WHERE clauses to exclude NULLs
  unless the user specifically asks about missing/unrecorded values.
- Use appropriate WHERE filters for conditions mentioned by the user.
- For example, if a target/outcome/diagnosis column uses 1 to represent
  that a patient has the condition, filter using that value when appropriate.
- Use only columns that actually exist in the supplied schema.

Question: {question}

SQL:"""

    response = _get_sql_llm().invoke(prompt)

    sql = _response_text(response)

    # Remove markdown fences if Gemini adds them.
    sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql


# ---------------------------------------------------------
# Format database result
# ---------------------------------------------------------
#
# IMPORTANT:
# This function does NOT call Gemini.
#
# It simply converts the SQLite result into a clear structured
# text format that the MAIN AGENT can understand.
#
# The main agent will use this information when generating the
# final answer.
# ---------------------------------------------------------


def _format_db_result(
    question: str,
    sql: str,
    columns: list,
    rows: list,
) -> str:
    """
    Format the SQLite result for the main agent without making
    another Gemini API call.
    """

    if not rows:
        return (
            "Database query result:\n"
            "No matching records were found.\n\n"
            f"Original question: {question}"
        )

    # Limit the number of rows returned to the main agent.
    #
    # This prevents very large database results from consuming
    # unnecessary context/tokens.
    preview = rows[:50]

    result_lines = [
        "Database query result:",
        f"Original question: {question}",
        f"SQL: {sql}",
        f"Columns: {columns}",
        f"Rows returned: {len(rows)}",
        "",
        "Data:",
    ]

    for row in preview:
        result_lines.append(str(row))

    if len(rows) > 50:
        result_lines.append(f"\nOnly the first 50 rows are shown out of {len(rows)} total rows.")

    return "\n".join(result_lines)


# ---------------------------------------------------------
# Create database tool runner
# ---------------------------------------------------------


def _make_db_tool(db_filename: str, table_name: str):
    """
    Return a function that runs the database pipeline:

        Natural language question
                ↓
        Get real database schema
                ↓
        Gemini generates SQL
                ↓
        SQL safety validation
                ↓
        SQLite execution
                ↓
        Structured result

    Gemini is NOT called again to summarize the result.
    """

    db_path = os.path.join(DB_DIR, db_filename)

    def _run(question: str) -> str:
        # -------------------------------------------------
        # Step 1: Get the real database schema
        # -------------------------------------------------

        schema_sql = get_table_schema(
            db_path,
            table_name,
        )

        if not schema_sql:
            return (
                f"Database error: table '{table_name}' not found in "
                f"{db_filename}. Did you run scripts/build_databases.py?"
            )

        # -------------------------------------------------
        # Step 2: Ask Gemini to generate SQL
        # -------------------------------------------------

        try:
            sql = _generate_sql(
                question,
                schema_sql,
                table_name,
            )

        except Exception as e:
            return (
                f"Could not generate the database query: {e}. Please try rephrasing the question."
            )

        # -------------------------------------------------
        # Step 3: Validate and execute the SQL
        # -------------------------------------------------

        try:
            columns, rows = run_read_only_query(
                db_path,
                sql,
            )

        except UnsafeSQLError as e:
            return f"I couldn't safely run that query ({e}). Try rephrasing the question."

        except Exception as e:
            return f"The database query failed: {e}. Try rephrasing the question."

        # -------------------------------------------------
        # Step 4: Return structured result
        #
        # NO SECOND GEMINI CALL HERE.
        # -------------------------------------------------

        return _format_db_result(
            question,
            sql,
            columns,
            rows,
        )

    return _run


# ---------------------------------------------------------
# Create runners for the three databases
# ---------------------------------------------------------

_heart_disease_runner = _make_db_tool(
    "heart_disease.db",
    "heart_disease",
)

_cancer_runner = _make_db_tool(
    "cancer.db",
    "cancer",
)

_diabetes_runner = _make_db_tool(
    "diabetes.db",
    "diabetes",
)


# ---------------------------------------------------------------------------
# Heart Disease database tool
# ---------------------------------------------------------------------------


@tool
def heart_disease_db_tool(question: str) -> str:
    """Use this tool for STATISTICS or DATA questions about the heart
    disease dataset: patient counts, averages (age, cholesterol, blood
    pressure, max heart rate), or filters on recorded patient records.

    Examples:
    - "What is the average age of patients with heart disease?"
    - "How many patients have a cholesterol level above 250?"

    Do NOT use this for general questions about what heart disease IS,
    its symptoms, causes, prevention, or treatment. Use the web search
    tool for those questions instead.
    """
    return _heart_disease_runner(question)


# ---------------------------------------------------------------------------
# Cancer database tool
# ---------------------------------------------------------------------------


@tool
def cancer_db_tool(question: str) -> str:
    """Use this tool for STATISTICS or DATA questions about the cancer
    prediction dataset: patient counts, averages (age, BMI), or filters
    on recorded patient records such as smoking status or genetic risk.

    Examples:
    - "How many patients in the dataset were diagnosed with cancer?"
    - "What is the average BMI of smokers in the dataset?"

    Do NOT use this for general questions about what cancer IS,
    its symptoms, causes, prevention, or treatment. Use the web search
    tool for those questions instead.
    """
    return _cancer_runner(question)


# ---------------------------------------------------------------------------
# Diabetes database tool
# ---------------------------------------------------------------------------


@tool
def diabetes_db_tool(question: str) -> str:
    """Use this tool for STATISTICS or DATA questions about the diabetes
    dataset: patient counts, averages (glucose, BMI, blood pressure,
    insulin), or filters on recorded patient records.

    Examples:
    - "How many patients have a glucose level over 140?"
    - "What is the average BMI of diabetic patients in the dataset?"

    Do NOT use this for general questions about what diabetes IS,
    its symptoms, causes, prevention, or treatment. Use the web search
    tool for those questions instead.
    """
    return _diabetes_runner(question)
