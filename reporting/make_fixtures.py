"""Create example result and report files for teammates.

Run from the project root:  python -m reporting.make_fixtures
"""
import json
from pathlib import Path

import pandas as pd

from cleaning.engine import apply_plan
from reporting.validator import validate_result
from reporting.exporter import build_exports

OUTPUT_DIR = Path(__file__).parent / "fixtures"


def main():
    original = pd.DataFrame(
        {
            "id": ["00123", "00456", "00123", "00789"],
            "name": ["  Ali ", "Sara", "  Ali ", "Zain"],
            "joined": ["03/04/2026", "15/01/2026", "03/04/2026", "not a date"],
            "city": ["Lahore", "NA", "Lahore", "Peshawar"],
        },
        dtype="string",
    )
    plan = [
        {"id": "op_001", "operation": "trim_whitespace",
         "columns": ["name"], "reason": "Extra spaces found."},
        {"id": "op_002", "operation": "remove_duplicates",
         "reason": "Duplicate rows found."},
        {"id": "op_003", "operation": "standardize_missing",
         "columns": ["city"], "markers": ["NA"], "reason": "NA markers found."},
        {"id": "op_004", "operation": "normalize_dates",
         "columns": ["joined"], "input_format": "%d/%m/%Y",
         "reason": "Standardize dates."},
    ]

    cleaned, log = apply_plan(original, plan)
    validation = validate_result(original, cleaned, plan, log)
    files = build_exports(
        cleaned,
        {"original_rows": len(original), "log": log, "validation": validation},
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    original.to_csv(OUTPUT_DIR / "original_example.csv", index=False)
    (OUTPUT_DIR / "cleaned_example.csv").write_bytes(files["csv"])
    (OUTPUT_DIR / "change_report_example.txt").write_bytes(files["report"])
    (OUTPUT_DIR / "example_plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )
    print(f"Example files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()