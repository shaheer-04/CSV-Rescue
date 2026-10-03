def _describe(entry):
    """Turn one change-log entry into a short readable sentence."""
    details = entry["details"]
    name = entry["operation"]

    if name == "trim_whitespace":
        return f"{details['changed_cells']} cell(s) trimmed"

    if name == "remove_duplicates":
        text = f"{details['removed_rows']} duplicate row(s) removed"
        if details["removed_row_indexes"]:
            text += f" (row indexes: {details['removed_row_indexes']})"
        return text

    if name == "standardize_missing":
        return f"{details['changed_cells']} missing-value marker(s) set to empty"

    if name == "change_case":
        return f"{details['changed_cells']} cell(s) changed to {details['case']} case"

    if name == "normalize_dates":
        text = (
            f"{details['changed_cells']} date(s) converted "
            f"from {details['input_format']}"
        )
        for column, rows in details["failed_rows"].items():
            if rows:
                text += (
                    f"; {len(rows)} value(s) in '{column}' could not be "
                    f"converted and were kept (row indexes: {rows})"
                )
        return text

    if name == "rename_columns":
        renamed = details["renamed_columns"]
        text = f"{len(renamed)} column(s) renamed"
        if renamed:
            pairs = ", ".join(f"{old} -> {new}" for old, new in renamed.items())
            text += f": {pairs}"
        return text

    return str(details)


def _build_report_text(cleaned, reports):
    log = reports.get("log", [])
    validation = reports.get(
        "validation",
        {"checks": [], "unresolved_issues": [], "all_passed": True},
    )

    lines = ["CSV Rescue - Change Report", "=" * 26, ""]

    original_rows = reports.get("original_rows")
    if original_rows is not None:
        lines.append(f"Rows before cleaning: {original_rows}")
    lines.append(f"Rows after cleaning: {len(cleaned)}")
    lines.append(f"Columns: {', '.join(str(c) for c in cleaned.columns)}")
    lines.append("")

    lines.append("Operations applied")
    lines.append("-" * 18)
    if not log:
        lines.append("No operations were applied.")
    for entry in log:
        lines.append(f"{entry['step']}. [{entry['id']}] {entry['operation']}")
        if entry.get("reason"):
            lines.append(f"   Reason: {entry['reason']}")
        lines.append(f"   Result: {_describe(entry)}")
        lines.append(f"   Rows: {entry['rows_before']} -> {entry['rows_after']}")
    lines.append("")

    status = "PASSED" if validation.get("all_passed", True) else "FAILED"
    lines.append(f"Validation: {status}")
    lines.append("-" * 18)
    for check in validation.get("checks", []):
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{mark}  {check['name']}: {check['message']}")
    lines.append("")

    lines.append("Unresolved issues")
    lines.append("-" * 17)
    issues = validation.get("unresolved_issues", [])
    if not issues:
        lines.append("None.")
    for issue in issues:
        lines.append(f"- {issue['message']}")

    return "\n".join(lines) + "\n"


def build_exports(cleaned, reports):
    """Build the downloadable files.

    `reports` is a dict with:
      "log": the change log from apply_plan
      "validation": the result from validate_result
      "original_rows": number of rows before cleaning (optional)

    Returns {"csv": bytes, "report": bytes}.
    """
    csv_bytes = cleaned.to_csv(index=False, na_rep="").encode("utf-8")
    report_bytes = _build_report_text(cleaned, reports).encode("utf-8")
    return {"csv": csv_bytes, "report": report_bytes}