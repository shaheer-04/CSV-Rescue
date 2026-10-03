import pandas as pd
import pytest

from cleaning.operations import (
    trim_whitespace,
    remove_duplicates,
    standardize_missing,
    rename_columns,
    change_case,
)
from cleaning.engine import apply_plan
from reporting.validator import validate_result
from reporting.exporter import build_exports

def test_trim_whitespace_removes_spaces():
    original = pd.DataFrame({"name": ["  Ali ", "Sara", " Zain"]}, dtype="string")

    cleaned, log = trim_whitespace(original, ["name"])

    assert cleaned["name"].tolist() == ["Ali", "Sara", "Zain"]
    assert log["changed_cells"] == 2


def test_trim_whitespace_keeps_original_unchanged():
    original = pd.DataFrame({"name": ["  Ali "]}, dtype="string")

    trim_whitespace(original, ["name"])

    assert original["name"].tolist() == ["  Ali "]


def test_trim_whitespace_rejects_unknown_column():
    original = pd.DataFrame({"name": ["Ali"]}, dtype="string")

    with pytest.raises(ValueError):
        trim_whitespace(original, ["age"])



def test_remove_duplicates_removes_exact_copies():
    original = pd.DataFrame(
        {"id": ["1", "2", "1"], "name": ["Ali", "Sara", "Ali"]}, dtype="string"
    )

    cleaned, log = remove_duplicates(original)

    assert len(cleaned) == 2
    assert log["removed_rows"] == 1
    assert log["removed_row_indexes"] == [2]


def test_remove_duplicates_keeps_original_unchanged():
    original = pd.DataFrame({"id": ["1", "1"]}, dtype="string")

    remove_duplicates(original)

    assert len(original) == 2





def test_standardize_missing_replaces_markers():
    original = pd.DataFrame(
        {"city": ["Lahore", "NA", "n/a", " ", "Karachi"]}, dtype="string"
    )

    cleaned, log = standardize_missing(original, ["city"], ["NA", "n/a", ""])

    assert cleaned["city"].isna().tolist() == [False, True, True, True, False]
    assert log["changed_cells"] == 3


def test_standardize_missing_keeps_original_unchanged():
    original = pd.DataFrame({"city": ["NA"]}, dtype="string")

    standardize_missing(original, ["city"], ["NA"])

    assert original["city"].tolist() == ["NA"]


def test_standardize_missing_ignores_other_columns():
    original = pd.DataFrame(
        {"id": ["00123", "NA"], "city": ["NA", "Lahore"]}, dtype="string"
    )

    cleaned, log = standardize_missing(original, ["city"], ["NA"])

    assert cleaned["id"].tolist() == ["00123", "NA"]
    assert log["changed_cells"] == 1





def test_rename_columns_renames_and_logs():
    original = pd.DataFrame({"cust_nm": ["Ali"], "age": ["20"]}, dtype="string")

    cleaned, log = rename_columns(original, {"cust_nm": "customer_name"})

    assert list(cleaned.columns) == ["customer_name", "age"]
    assert log["renamed_columns"] == {"cust_nm": "customer_name"}


def test_rename_columns_keeps_original_unchanged():
    original = pd.DataFrame({"cust_nm": ["Ali"]}, dtype="string")

    rename_columns(original, {"cust_nm": "customer_name"})

    assert list(original.columns) == ["cust_nm"]


def test_rename_columns_rejects_unknown_column():
    original = pd.DataFrame({"name": ["Ali"]}, dtype="string")

    with pytest.raises(ValueError):
        rename_columns(original, {"missing": "x"})


def test_rename_columns_rejects_duplicate_names():
    original = pd.DataFrame({"a": ["1"], "b": ["2"]}, dtype="string")

    with pytest.raises(ValueError):
        rename_columns(original, {"a": "b"})


def test_rename_columns_rejects_empty_name():
    original = pd.DataFrame({"a": ["1"]}, dtype="string")

    with pytest.raises(ValueError):
        rename_columns(original, {"a": "  "})




def _sample_plan():
    return [
        {"id": "op_001", "operation": "trim_whitespace",
         "columns": ["name"], "reason": "Extra spaces found."},
        {"id": "op_002", "operation": "remove_duplicates",
         "reason": "Duplicate rows found."},
    ]


def test_apply_plan_runs_in_order_and_logs():
    original = pd.DataFrame({"name": [" Ali", "Ali", "Sara"]}, dtype="string")

    cleaned, log = apply_plan(original, _sample_plan())

    assert len(cleaned) == 2
    assert [entry["id"] for entry in log] == ["op_001", "op_002"]
    assert log[0]["rows_before"] == 3
    assert log[1]["rows_after"] == 2
    assert log[1]["details"]["removed_rows"] == 1


def test_apply_plan_order_changes_result():
    original = pd.DataFrame({"name": [" Ali", "Ali", "Sara"]}, dtype="string")
    reversed_plan = list(reversed(_sample_plan()))

    cleaned, log = apply_plan(original, reversed_plan)

    assert len(cleaned) == 3
    assert log[0]["details"]["removed_rows"] == 0


def test_apply_plan_keeps_original_unchanged():
    original = pd.DataFrame({"name": [" Ali", "Ali"]}, dtype="string")

    apply_plan(original, _sample_plan())

    assert original["name"].tolist() == [" Ali", "Ali"]


def test_apply_plan_rejects_unknown_operation():
    original = pd.DataFrame({"name": ["Ali"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "delete_everything", "reason": "x"}]

    with pytest.raises(ValueError):
        apply_plan(original, plan)


def test_apply_plan_rejects_missing_parameter():
    original = pd.DataFrame({"name": ["Ali"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "trim_whitespace", "reason": "x"}]

    with pytest.raises(ValueError):
        apply_plan(original, plan)



def test_validate_result_passes_for_a_clean_run():
    original = pd.DataFrame({"name": [" Ali", "Ali", "Sara"]}, dtype="string")
    plan = _sample_plan()
    cleaned, log = apply_plan(original, plan)

    result = validate_result(original, cleaned, plan, log)

    assert result["all_passed"] is True
    assert result["unresolved_issues"] == []


def test_validate_result_reports_remaining_duplicates():
    original = pd.DataFrame({"name": ["Ali", "Ali"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "trim_whitespace",
             "columns": ["name"], "reason": "x"}]
    cleaned, log = apply_plan(original, plan)

    result = validate_result(original, cleaned, plan, log)

    assert result["all_passed"] is True
    assert result["unresolved_issues"][0]["type"] == "duplicate_rows"


def test_validate_result_fails_when_rows_do_not_match_log():
    original = pd.DataFrame({"name": [" Ali", "Ali", "Sara"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "trim_whitespace",
             "columns": ["name"], "reason": "x"}]
    cleaned, log = apply_plan(original, plan)
    cleaned = cleaned.iloc[:2]

    result = validate_result(original, cleaned, plan, log)

    assert result["all_passed"] is False


def test_validate_result_reports_remaining_whitespace():
    original = pd.DataFrame({"name": ["Ali ", "Sara"]}, dtype="string")
    cleaned, log = apply_plan(original, [])

    result = validate_result(original, cleaned, [], log)

    issue_types = [issue["type"] for issue in result["unresolved_issues"]]
    assert "whitespace" in issue_types

def test_export_csv_keeps_leading_zeros():
    cleaned = pd.DataFrame({"id": ["00123"], "name": ["Ali"]}, dtype="string")

    files = build_exports(cleaned, {"log": []})

    assert "00123,Ali" in files["csv"].decode("utf-8")


def test_export_csv_has_no_index_and_empty_missing_values():
    cleaned = pd.DataFrame(
        {"id": ["1", "2"], "city": ["Lahore", pd.NA]}, dtype="string"
    )

    files = build_exports(cleaned, {"log": []})

    assert files["csv"].decode("utf-8").splitlines() == [
        "id,city",
        "1,Lahore",
        "2,",
    ]


def test_export_report_describes_operations():
    original = pd.DataFrame({"name": [" Ali", "Ali", "Sara"]}, dtype="string")
    plan = _sample_plan()
    cleaned, log = apply_plan(original, plan)
    validation = validate_result(original, cleaned, plan, log)
    reports = {"original_rows": 3, "log": log, "validation": validation}

    text = build_exports(cleaned, reports)["report"].decode("utf-8")

    assert "op_001" in text
    assert "op_002" in text
    assert "1 duplicate row(s) removed" in text
    assert "Rows before cleaning: 3" in text
    assert "Rows after cleaning: 2" in text
    assert "Validation: PASSED" in text


def test_export_report_shows_failed_checks():
    cleaned = pd.DataFrame({"name": ["Ali"]}, dtype="string")
    validation = {
        "checks": [{"name": "row_count_matches_log", "passed": False,
                    "message": "Row counts differ."}],
        "unresolved_issues": [],
        "all_passed": False,
    }

    text = build_exports(cleaned, {"log": [], "validation": validation})[
        "report"
    ].decode("utf-8")

    assert "Validation: FAILED" in text
    assert "FAIL  row_count_matches_log" in text


def test_export_report_lists_unresolved_issues():
    cleaned = pd.DataFrame({"name": ["Ali", "Ali"]}, dtype="string")
    validation = {
        "checks": [],
        "unresolved_issues": [{"type": "duplicate_rows", "count": 1,
                               "message": "1 duplicate row(s) remain."}],
        "all_passed": True,
    }

    text = build_exports(cleaned, {"log": [], "validation": validation})[
        "report"
    ].decode("utf-8")

    assert "1 duplicate row(s) remain." in text



def test_change_case_converts_text():
    original = pd.DataFrame(
        {"city": ["lahore", "KARACHI", "Peshawar"]}, dtype="string"
    )

    cleaned, log = change_case(original, ["city"], "title")

    assert cleaned["city"].tolist() == ["Lahore", "Karachi", "Peshawar"]
    assert log["changed_cells"] == 2


def test_change_case_keeps_original_unchanged():
    original = pd.DataFrame({"city": ["lahore"]}, dtype="string")

    change_case(original, ["city"], "upper")

    assert original["city"].tolist() == ["lahore"]


def test_change_case_rejects_invalid_case():
    original = pd.DataFrame({"city": ["lahore"]}, dtype="string")

    with pytest.raises(ValueError):
        change_case(original, ["city"], "sideways")


def test_change_case_rejects_unknown_column():
    original = pd.DataFrame({"city": ["lahore"]}, dtype="string")

    with pytest.raises(ValueError):
        change_case(original, ["country"], "lower")


def test_engine_runs_change_case():
    original = pd.DataFrame({"city": ["ali"]}, dtype="string")
    plan = [{"id": "op_001", "operation": "change_case",
             "columns": ["city"], "case": "upper", "reason": "Make consistent."}]

    cleaned, log = apply_plan(original, plan)

    assert cleaned["city"].tolist() == ["ALI"]
    assert log[0]["details"]["case"] == "upper"