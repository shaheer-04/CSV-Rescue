import pandas as pd
import pytest

from cleaning.operations import normalize_dates
from cleaning.engine import apply_plan
from reporting.validator import validate_result
from reporting.exporter import build_exports


def test_normalize_dates_converts_with_chosen_format():
    original = pd.DataFrame({"date": ["03/04/2026", " 15/01/2026"]}, dtype="string")

    cleaned, log = normalize_dates(original, ["date"], "%d/%m/%Y")

    assert cleaned["date"].tolist() == ["2026-04-03", "2026-01-15"]
    assert log["changed_cells"] == 2


def test_normalize_dates_format_choice_changes_ambiguous_date():
    original = pd.DataFrame({"date": ["03/04/2026"]}, dtype="string")

    day_first, _ = normalize_dates(original, ["date"], "%d/%m/%Y")
    month_first, _ = normalize_dates(original, ["date"], "%m/%d/%Y")

    assert day_first["date"].tolist() == ["2026-04-03"]
    assert month_first["date"].tolist() == ["2026-03-04"]


def test_normalize_dates_keeps_failed_values_and_reports_rows():
    original = pd.DataFrame(
        {"date": ["03/04/2026", "not a date", "31/02/2026"]}, dtype="string"
    )

    cleaned, log = normalize_dates(original, ["date"], "%d/%m/%Y")

    assert cleaned["date"].tolist() == ["2026-04-03", "not a date", "31/02/2026"]
    assert log["failed_rows"] == {"date": [1, 2]}


def test_normalize_dates_leaves_empty_and_missing_alone():
    original = pd.DataFrame({"date": ["", pd.NA, "03/04/2026"]}, dtype="string")

    cleaned, log = normalize_dates(original, ["date"], "%d/%m/%Y")

    assert cleaned["date"].tolist()[0] == ""
    assert pd.isna(cleaned["date"].tolist()[1])
    assert log["failed_rows"] == {"date": []}


def test_normalize_dates_keeps_original_and_other_columns_unchanged():
    original = pd.DataFrame(
        {"id": ["00123"], "date": ["03/04/2026"]}, dtype="string"
    )

    cleaned, _ = normalize_dates(original, ["date"], "%d/%m/%Y")

    assert original["date"].tolist() == ["03/04/2026"]
    assert cleaned["id"].tolist() == ["00123"]


def test_normalize_dates_requires_format_and_known_column():
    original = pd.DataFrame({"date": ["03/04/2026"]}, dtype="string")

    with pytest.raises(ValueError):
        normalize_dates(original, ["date"], "  ")
    with pytest.raises(ValueError):
        normalize_dates(original, ["missing"], "%d/%m/%Y")


def test_report_lists_failed_date_rows():
    original = pd.DataFrame({"date": ["03/04/2026", "bad"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "normalize_dates",
             "columns": ["date"], "input_format": "%d/%m/%Y",
             "reason": "Standardize dates."}]
    cleaned, log = apply_plan(original, plan)
    validation = validate_result(original, cleaned, plan, log)

    text = build_exports(
        cleaned, {"original_rows": 2, "log": log, "validation": validation}
    )["report"].decode("utf-8")

    assert "1 date(s) converted" in text
    assert "could not be converted" in text
    assert "row indexes: [1]" in text