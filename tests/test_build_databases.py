"""
Unit tests for the medical-specific cleaning logic in
scripts/build_databases.py — in particular, the zero-as-missing rule, which
is the one piece of domain-specific logic in this whole pipeline and is
exactly the kind of thing worth pinning down with a test (it's already
caught one real bug during development — see build_databases.py's git
history / the ZERO_AS_MISSING_KEYWORDS comment for the "trestbps" gap).
"""

import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from build_databases import clean_column_name, clean_dataframe


def test_clean_column_name_normalizes_spacing_and_case():
    assert clean_column_name("Resting BP") == "resting_bp"
    assert clean_column_name(" Age ") == "age"


def test_zero_is_converted_to_null_for_known_measurement_columns():
    df = pd.DataFrame({"Glucose": [148, 0, 183], "BMI": [33.6, 0.0, 23.3]})
    cleaned = clean_dataframe(df)
    assert pd.isna(cleaned["glucose"].iloc[1])
    assert pd.isna(cleaned["bmi"].iloc[1])
    # Non-zero values must be left untouched.
    assert cleaned["glucose"].iloc[0] == 148


def test_zero_is_converted_for_abbreviated_column_names():
    # Regression test for the real bug found during development: "trestbps"
    # (Cleveland heart disease dataset's actual column name for resting
    # blood pressure) doesn't contain the word "pressure", so it needs its
    # own explicit keyword entry.
    df = pd.DataFrame({"trestbps": [145, 0, 130], "thalach": [150, 0, 172]})
    cleaned = clean_dataframe(df)
    assert pd.isna(cleaned["trestbps"].iloc[1])
    assert pd.isna(cleaned["thalach"].iloc[1])


def test_zero_is_left_alone_for_unrelated_columns():
    # A 0 in a column like "sex" (0/1 encoded) or "smoking" (0/1 encoded) is
    # a real, meaningful value, not a missing-data sentinel — must NOT be
    # touched by the zero-as-missing rule.
    df = pd.DataFrame({"sex": [0, 1, 0], "smoking": [1, 0, 0]})
    cleaned = clean_dataframe(df)
    assert cleaned["sex"].tolist() == [0, 1, 0]
    assert cleaned["smoking"].tolist() == [1, 0, 0]


def test_clean_dataframe_converts_comma_numbers_to_int():
    df = pd.DataFrame({"patient_count": ["1,200", "500"]})
    cleaned = clean_dataframe(df)
    assert cleaned["patient_count"].tolist() == [1200, 500]


def test_clean_dataframe_drops_exact_duplicates():
    df = pd.DataFrame({"age": [50, 50], "glucose": [148, 148]})
    cleaned = clean_dataframe(df)
    assert len(cleaned) == 1
