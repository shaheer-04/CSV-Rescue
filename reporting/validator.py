import pandas as pd


def _as_dict(operation):
    """Accept either a plain dict or a Pydantic model."""
    if hasattr(operation, "model_dump"):
        return operation.model_dump()
    return dict(operation)


def validate_result(original, cleaned, plan, log):
    """Check that the cleaned data, the plan, and the change log agree.

    Returns:
      checks: integrity checks, each with a name, a pass/fail flag, and a message
      unresolved_issues: problems that still remain in the cleaned data
      all_passed: True only if every integrity check passed
    """
    plan = [_as_dict(op) for op in plan]
    checks = []

    def add(name, passed, message):
        checks.append({"name": name, "passed": bool(passed), "message": message})

    # 1. The original and the cleaned data must be separate objects.
    add(
        "original_separate",
        cleaned is not original,
        "Cleaned data is a separate copy from the original.",
    )

    # 2. Row counts must match what the log says was removed.
    removed = sum(entry["details"].get("removed_rows", 0) for entry in log)
    expected_rows = len(original) - removed
    add(
        "row_count_matches_log",
        len(cleaned) == expected_rows,
        f"Expected {expected_rows} rows from the log, found {len(cleaned)}.",
    )

    # 3. Column names must match the renames recorded in the log.
    expected_columns = list(original.columns)
    for entry in log:
        renamed = entry["details"].get("renamed_columns", {})
        expected_columns = [renamed.get(col, col) for col in expected_columns]
    add(
        "columns_match_log",
        list(cleaned.columns) == expected_columns,
        "Column names match the renames recorded in the log.",
    )

    # 4. The log must list the same operations, in the same order, as the plan.
    plan_ids = [op.get("id", f"step_{i}") for i, op in enumerate(plan, start=1)]
    log_ids = [entry["id"] for entry in log]
    add(
        "log_matches_plan",
        plan_ids == log_ids,
        "Change log lists the same operations as the approved plan, in order.",
    )

    # Problems that remain in the cleaned data (not failures, but visible to the user).
    unresolved = []

    duplicate_count = int(cleaned.duplicated().sum())
    if duplicate_count > 0:
        unresolved.append(
            {
                "type": "duplicate_rows",
                "count": duplicate_count,
                "message": f"{duplicate_count} duplicate row(s) remain.",
            }
        )

    for column in cleaned.columns:
        values = cleaned[column].astype("string")
        stripped = values.str.strip()
        spaced = int(values.ne(stripped).fillna(False).sum())
        if spaced > 0:
            unresolved.append(
                {
                    "type": "whitespace",
                    "column": column,
                    "count": spaced,
                    "message": (
                        f"{spaced} value(s) in '{column}' still have "
                        "leading or trailing spaces."
                    ),
                }
            )

    return {
        "checks": checks,
        "unresolved_issues": unresolved,
        "all_passed": all(check["passed"] for check in checks),
    }