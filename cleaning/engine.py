from cleaning.operations import (
    trim_whitespace,
    remove_duplicates,
    standardize_missing,
    rename_columns,
    change_case,
    normalize_dates,
)

# The fixed list of supported operations, and the parameters each one needs.
OPERATIONS = {
    "trim_whitespace": {
        "required": ["columns"],
        "run": lambda df, op: trim_whitespace(df, op["columns"]),
    },
    "remove_duplicates": {
        "required": [],
        "run": lambda df, op: remove_duplicates(df),
    },
    "standardize_missing": {
        "required": ["columns", "markers"],
        "run": lambda df, op: standardize_missing(df, op["columns"], op["markers"]),
    },
    "rename_columns": {
        "required": ["mapping"],
        "run": lambda df, op: rename_columns(df, op["mapping"]),
    },
    "change_case": {
        "required": ["columns", "case"],
        "run": lambda df, op: change_case(df, op["columns"], op["case"]),
    },
    "normalize_dates": {
        "required": ["columns", "input_format"],
        "run": lambda df, op: normalize_dates(df, op["columns"], op["input_format"]),
    },
}


def _as_dict(operation):
    """Accept either a plain dict or a Pydantic model."""
    if hasattr(operation, "model_dump"):
        return operation.model_dump()
    return dict(operation)


def _check_plan(plan):
    """Check the whole plan before running anything."""
    for position, op in enumerate(plan, start=1):
        name = op.get("operation")
        if name not in OPERATIONS:
            raise ValueError(f"Step {position}: unsupported operation '{name}'.")
        for key in OPERATIONS[name]["required"]:
            if key not in op:
                raise ValueError(
                    f"Step {position} ({name}): missing parameter '{key}'."
                )


def apply_plan(original, approved_plan):
    """Run approved operations in order on a copy of the data.

    Returns the cleaned data and a change log with one entry per operation.
    The original data is never changed. If the plan is invalid, nothing runs.
    """
    plan = [_as_dict(op) for op in approved_plan]
    _check_plan(plan)

    cleaned = original.copy(deep=True)
    log = []

    for position, op in enumerate(plan, start=1):
        rows_before = len(cleaned)
        cleaned, details = OPERATIONS[op["operation"]]["run"](cleaned, op)
        log.append(
            {
                "step": position,
                "id": op.get("id", f"step_{position}"),
                "operation": op["operation"],
                "reason": op.get("reason", ""),
                "rows_before": rows_before,
                "rows_after": len(cleaned),
                "details": details,
            }
        )

    return cleaned, log