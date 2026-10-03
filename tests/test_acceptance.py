from io import BytesIO

import pandas as pd
import pytest

from cleaning.engine import apply_plan
from reporting.validator import validate_result
from reporting.exporter import build_exports


def _messy_data():
    return pd.DataFrame(
        {
            "id": ["00123", "00456", "00123", "00789"],
            "name": ["  Ali ", "Sara", "  Ali ", "Zain"],
            "joined": ["03/04/2026", "15/01/2026", "03/04/2026", "not a date"],
            "city": ["Lahore", "NA", "Lahore", "Peshawar"],
        },
        dtype="string",
    )


def _full_plan():
    return [
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


def _run(original, plan):
    cleaned, log = apply_plan(original, plan)
    validation = validate_result(original, cleaned, plan, log)
    reports = {"original_rows": len(original), "log": log, "validation": validation}
    return cleaned, log, validation, build_exports(cleaned, reports)


def test_identifier_with_leading_zeros_is_unchanged():
    cleaned, _, _, _ = _run(_messy_data(), _full_plan())

    assert cleaned["id"].tolist() == ["00123", "00456", "00789"]


def test_ambiguous_date_needs_a_format_choice():
    plan = [{"id": "op_001", "operation": "normalize_dates",
             "columns": ["joined"], "reason": "Standardize dates."}]

    with pytest.raises(ValueError):
        apply_plan(_messy_data(), plan)


def test_invalid_date_keeps_original_value_and_report_flags_row():
    cleaned, log, _, files = _run(_messy_data(), _full_plan())

    assert "not a date" in cleaned["joined"].tolist()
    assert log[3]["details"]["failed_rows"]["joined"] == [3]
    assert "could not be converted" in files["report"].decode("utf-8")


def test_only_approved_duplicates_are_removed_and_counts_match():
    original = _messy_data()
    cleaned, log, validation, _ = _run(original, _full_plan())

    assert len(cleaned) == 3
    assert log[1]["details"]["removed_rows"] == 1
    assert len(original) - log[1]["details"]["removed_rows"] == len(cleaned)
    assert validation["all_passed"] is True


def test_unapproved_operation_does_not_run():
    approved_only = [_full_plan()[0]]

    cleaned, log, validation, _ = _run(_messy_data(), approved_only)

    assert len(log) == 1
    assert len(cleaned) == 4
    assert "NA" in cleaned["city"].tolist()
    assert validation["unresolved_issues"][0]["type"] == "duplicate_rows"


def test_original_data_is_never_changed():
    original = _messy_data()
    snapshot = original.copy(deep=True)

    _run(original, _full_plan())

    pd.testing.assert_frame_equal(original, snapshot)


def test_downloaded_csv_matches_cleaned_data():
    cleaned, _, _, files = _run(_messy_data(), _full_plan())

    downloaded = pd.read_csv(
        BytesIO(files["csv"]), dtype="string", keep_default_na=False
    )

    assert downloaded.shape == cleaned.shape
    assert downloaded["id"].tolist() == ["00123", "00456", "00789"]
    assert downloaded["joined"].tolist() == ["2026-04-03", "2026-01-15", "not a date"]
    assert downloaded["city"].tolist() == ["Lahore", "", "Peshawar"]


def test_report_matches_actual_changes():
    _, _, _, files = _run(_messy_data(), _full_plan())
    text = files["report"].decode("utf-8")

    assert "Rows before cleaning: 4" in text
    assert "Rows after cleaning: 3" in text
    assert "1 duplicate row(s) removed" in text
    assert "1 missing-value marker(s) set to empty" in text
    assert "Validation: PASSED" in text