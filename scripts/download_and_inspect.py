"""
STEP 2: Download the three medical datasets from Kaggle and inspect them.

WHY WE DON'T HARDCODE COLUMN NAMES
------------------------------------
Unlike some open dataset hubs, we don't know the exact column names/types
in these CSVs until we actually look at them. This script downloads each
dataset via the official `kaggle` Python package, then prints its real
schema, sample rows, and data-quality issues — the next script
(build_databases.py) reads from the CSVs this script saves, not from any
assumption baked into code.

KAGGLE AUTHENTICATION (do this once, before running this script)
--------------------------------------------------------------------
Kaggle's API requires an authenticated account — these datasets are NOT
anonymously downloadable like a plain CSV URL.

1. Log into kaggle.com -> click your profile picture -> "Settings".
2. Under "API", click "Create New Token" — this downloads a `kaggle.json`
   file containing your username and an API key.
3. Place that file at `~/.kaggle/kaggle.json` (on Windows:
   `C:\\Users\\<you>\\.kaggle\\kaggle.json`), then restrict its permissions:
       mkdir -p ~/.kaggle && mv kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
   (The `chmod` step matters: the kaggle package will refuse to run if the
   file is group/world-readable, since it contains a secret key.)

   Alternatively, set KAGGLE_USERNAME and KAGGLE_KEY as environment
   variables (e.g. in your .env) instead of creating the file — the kaggle
   package supports both methods.

IF YOU CAN'T GET KAGGLE AUTH WORKING / RUNNING THIS FROM A SANDBOX WITHOUT
NETWORK ACCESS TO kaggle.com: download the 3 CSVs manually via your browser
from the dataset pages linked in the README, and place them directly at:
    data/heart_disease.csv
    data/cancer.csv
    data/diabetes.csv
then skip straight to build_databases.py — it only needs those 3 files to
exist, it doesn't care how they got there.
"""

import os

# The kaggle package reads credentials from ~/.kaggle/kaggle.json (or
# KAGGLE_USERNAME/KAGGLE_KEY env vars) THE MOMENT it's imported — so if
# you're using a .env file for the env-var method, load it before this
# import, not after.
from dotenv import load_dotenv

load_dotenv()

import pandas as pd  # noqa: E402
from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# (kaggle dataset slug, output CSV filename, expected CSV name inside the zip)
# NOTE: Kaggle datasets can contain more than one file or get renamed by the
# uploader over time. If `download_dataset_csv` can't find a single obvious
# CSV, it lists what it DID find so you can adjust FILENAME_HINT below.
DATASETS = [
    {
        "slug": "johnsmith88/heart-disease-dataset",
        "short_name": "heart_disease",
        "filename_hint": "heart",  # case-insensitive substring match
    },
    {
        "slug": "rabieelkharoua/cancer-prediction-dataset",
        "short_name": "cancer",
        "filename_hint": "cancer",
    },
    {
        "slug": "iammustafatz/diabetes-prediction-dataset",
        "short_name": "diabetes",
        "filename_hint": "diabetes",
    },
]


def download_dataset_csv(api: KaggleApi, slug: str, short_name: str, filename_hint: str) -> str:
    """Downloads+unzips a Kaggle dataset into data/<short_name>_raw/, then
    finds the CSV inside it (by filename hint) and returns its path."""
    raw_dir = os.path.join(DATA_DIR, f"{short_name}_raw")
    os.makedirs(raw_dir, exist_ok=True)

    print(f"Downloading '{slug}' ...")
    api.dataset_download_files(slug, path=raw_dir, unzip=True)

    csv_files = [f for f in os.listdir(raw_dir) if f.lower().endswith(".csv")]
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found after downloading '{slug}' into {raw_dir}")

    # Prefer a file matching the hint; otherwise fall back to the first CSV
    # found (and print all candidates so you can sanity-check the choice).
    matched = [f for f in csv_files if filename_hint.lower() in f.lower()]
    chosen = matched[0] if matched else csv_files[0]
    if len(csv_files) > 1:
        print(f"  NOTE: multiple CSVs found {csv_files}, using '{chosen}'.")

    return os.path.join(raw_dir, chosen)


def inspect_dataframe(name: str, df: pd.DataFrame) -> None:
    """Prints a human-readable summary of a DataFrame's structure and quality."""
    print("\n" + "=" * 70)
    print(f"DATASET: {name}  |  rows={len(df)}  cols={len(df.columns)}")
    print("=" * 70)

    print("\n--- Columns & dtypes ---")
    print(df.dtypes)

    print("\n--- First 5 rows ---")
    with pd.option_context("display.max_columns", None, "display.width", 160):
        print(df.head(5))

    print("\n--- MESSY DATA CHECK ---")
    null_counts = df.isnull().sum()
    cols_with_nulls = null_counts[null_counts > 0]
    if len(cols_with_nulls) > 0:
        print("Columns with missing values:")
        print(cols_with_nulls)
    else:
        print("No missing values detected.")

    # Medical datasets commonly encode "missing" as 0 in columns where 0 is
    # biologically impossible (e.g. blood pressure, glucose, BMI = 0). This
    # is a well-known data-quality gotcha specific to this kind of data, so
    # we flag it explicitly rather than silently treating 0 as a real value.
    # NOTE: this keyword list is a heuristic and won't catch every
    # abbreviated column name (e.g. "trestbps" for blood pressure) — always
    # read the actual printed column names above and judge for yourself
    # whether a 0 makes biological sense for that specific column.
    zero_missing_keywords = [
        "pressure",
        "glucose",
        "bmi",
        "chol",
        "insulin",
        "thickness",
        "trestbps",
        "thalach",
    ]
    for col in df.select_dtypes(include="number").columns:
        if df[col].min() == 0 and any(keyword in col.lower() for keyword in zero_missing_keywords):
            zero_count = (df[col] == 0).sum()
            print(
                f"NOTE: column '{col}' has {zero_count} zero values — for a "
                f"measurement like this, 0 likely means 'missing/not recorded', "
                f"not a real biological value. Consider treating 0 as NULL for "
                f"this column before analysis."
            )

    duplicate_count = df.duplicated().sum()
    if duplicate_count > 0:
        print(f"NOTE: {duplicate_count} fully duplicated rows found.")


def main():
    api = KaggleApi()
    api.authenticate()  # raises a clear error immediately if kaggle.json/env vars aren't set up

    for entry in DATASETS:
        csv_path = download_dataset_csv(
            api, entry["slug"], entry["short_name"], entry["filename_hint"]
        )
        df = pd.read_csv(csv_path)
        inspect_dataframe(entry["short_name"], df)

        out_path = os.path.join(DATA_DIR, f"{entry['short_name']}.csv")
        df.to_csv(out_path, index=False)
        print(f"\nSaved clean copy -> {out_path}")

    print(
        "\nAll datasets downloaded and inspected. Review the printed output "
        "above (especially the zero-as-missing warnings), then run "
        "scripts/build_databases.py next."
    )


if __name__ == "__main__":
    main()
