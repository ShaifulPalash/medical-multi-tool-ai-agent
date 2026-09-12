"""
STEP 3: Convert the downloaded CSVs into SQLite databases.

Same general approach as any tabular-to-SQLite pipeline (clean, infer
types via pandas, write with SQLAlchemy) — see the inline comments for the
one medical-data-specific rule we add: zero-as-missing handling for
measurement columns.

OUTPUT
------
  db/heart_disease.db  -> table "heart_disease"
  db/cancer.db          -> table "cancer"
  db/diabetes.db        -> table "diabetes"
"""

import os
import re
import sqlite3

import pandas as pd
from sqlalchemy import create_engine

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")
os.makedirs(DB_DIR, exist_ok=True)

# short_name -> (csv filename, sqlite db filename, table name)
TABLES = {
    "heart_disease": ("heart_disease.csv", "heart_disease.db", "heart_disease"),
    "cancer": ("cancer.csv", "cancer.db", "cancer"),
    "diabetes": ("diabetes.csv", "diabetes.db", "diabetes"),
}

# Columns where a value of exactly 0 almost certainly means "not recorded"
# rather than a real biological reading (see download_and_inspect.py's
# MESSY DATA CHECK for the same logic applied at inspection time). Matched
# as a case-insensitive substring against the (already-normalized) column
# name.
#
# IMPORTANT: this is a heuristic keyword list, not a guarantee — medical
# datasets often use abbreviated column names (e.g. the classic Cleveland
# heart disease dataset uses "trestbps" for resting blood pressure and
# "thalach" for max heart rate, neither of which contains the full English
# word). ALWAYS cross-check this list against the real column names printed
# by download_and_inspect.py for YOUR actual downloaded CSVs, and add any
# abbreviation it misses.
ZERO_AS_MISSING_KEYWORDS = [
    "pressure",
    "glucose",
    "bmi",
    "chol",
    "insulin",
    "thickness",
    "trestbps",  # heart disease dataset: resting blood pressure
    "thalach",  # heart disease dataset: max heart rate achieved
]


def clean_column_name(col: str) -> str:
    """Lowercase, spaces/hyphens -> underscores, strip non-alphanumeric chars."""
    col = col.strip().lower()
    col = re.sub(r"[\s\-]+", "_", col)
    col = re.sub(r"[^a-z0-9_]", "", col)
    return col or "unnamed_col"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """General-purpose cleaning, safe for any of the 3 datasets."""
    df = df.copy()

    # 1. Normalize column names.
    df.columns = [clean_column_name(c) for c in df.columns]

    # 2. Strip whitespace from text cells; normalize empty strings to NaN.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"": None, "nan": None, "None": None})

    # 3. Convert text columns that are fully numeric (e.g. "1,200") into
    #    real numeric columns — only if EVERY non-null value converts cleanly.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        stripped = df[col].dropna().astype(str).str.replace(",", "", regex=False)
        if len(stripped) == 0:
            continue
        is_int = stripped.str.match(r"^-?\d+$").all()
        is_float = stripped.str.match(r"^-?\d+\.\d+$").all()
        if is_int:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False), errors="coerce"
            ).astype("Int64")
        elif is_float:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False), errors="coerce"
            )

    # 4. Medical-data-specific rule: for measurement columns where 0 is not
    #    biologically plausible (blood pressure, glucose, BMI, cholesterol,
    #    insulin, skin thickness), treat 0 as missing (NULL) rather than a
    #    real reading. We do NOT drop these rows — we just convert the
    #    sentinel 0 to NULL, so downstream SQL queries like AVG() aren't
    #    silently skewed by a bunch of impossible zero readings.
    for col in df.select_dtypes(include="number").columns:
        if any(keyword in col for keyword in ZERO_AS_MISSING_KEYWORDS):
            zero_count = (df[col] == 0).sum()
            if zero_count > 0:
                df.loc[df[col] == 0, col] = None
                print(f"  Converted {zero_count} zero values to NULL in column '{col}'.")

    # 5. Drop exact duplicate rows.
    df = df.drop_duplicates()

    return df


def build_one_database(short_name: str, csv_file: str, db_file: str, table_name: str):
    csv_path = os.path.join(DATA_DIR, csv_file)
    db_path = os.path.join(DB_DIR, db_file)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Missing {csv_path}. Run scripts/download_and_inspect.py first "
            f"(or manually place the CSV there — see that script's docstring)."
        )

    print(f"\nBuilding {db_file} from {csv_file} ...")
    df = pd.read_csv(csv_path)
    df = clean_dataframe(df)

    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    df.to_sql(table_name, engine, if_exists="replace", index=False)

    print(f"Built {db_path}  (table: {table_name}, rows: {len(df)})")
    print("Columns:", list(df.columns))

    conn = sqlite3.connect(db_path)
    schema_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()[0]
    print("Schema:\n", schema_sql)
    conn.close()


def main():
    for short_name, (csv_file, db_file, table_name) in TABLES.items():
        build_one_database(short_name, csv_file, db_file, table_name)

    print("\nAll three SQLite databases built successfully in ./db/")


if __name__ == "__main__":
    main()
