import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from cleaning.engine import apply_plan
from reporting.exporter import build_exports
from reporting.validator import validate_result


def render_cleaning_panel(original, source_name, input_signature):
    st.header("Review and apply cleaning")
    st.caption(
        "Manual mode: choose operations below. "
        "Your natural-language goal is not interpreted in this mode."
    )

    # Changing the file or parsing settings creates fresh controls.
    source_token = hashlib.sha256(
        repr(input_signature).encode()
    ).hexdigest()[:16]

    def key(name):
        return f"cleaning_{source_token}_{name}"

    columns = original.columns.tolist()
    plan = []

    def add(operation, reason, **parameters):
        plan.append({
            "id": f"op_{len(plan) + 1:03d}",
            "operation": operation,
            "reason": reason,
            **parameters,
        })

    st.subheader("1. Choose changes")

    with st.expander("Trim leading and trailing spaces", expanded=True):
        trim_columns = st.multiselect(
            "Columns to trim",
            columns,
            key=key("trim"),
        )
        if trim_columns:
            add(
                "trim_whitespace",
                "User selected whitespace cleanup.",
                columns=trim_columns,
            )

    with st.expander("Replace missing-value markers"):
        missing_columns = st.multiselect(
            "Columns containing placeholders",
            columns,
            key=key("missing_columns"),
        )
        markers_text = st.text_area(
            "Markers to replace, one per line",
            value="N/A\nNULL",
            key=key("markers"),
        )
        st.caption(
            "Matching ignores case and surrounding spaces. "
            "Selected markers become empty values; review their meaning."
        )
        markers = list(dict.fromkeys(
            line.strip()
            for line in markers_text.splitlines()
            if line.strip()
        ))

        if missing_columns and markers:
            add(
                "standardize_missing",
                "User approved these missing-value markers.",
                columns=missing_columns,
                markers=markers,
            )
        elif missing_columns:
            st.warning("Enter at least one marker to enable this operation.")

    with st.expander("Standardize text case"):
        case_columns = st.multiselect(
            "Columns to change",
            columns,
            key=key("case_columns"),
        )
        selected_case = st.selectbox(
            "Text case",
            ["lower", "upper", "title"],
            key=key("case"),
        )
        st.caption(
            "Case changes can affect identifiers and names. "
            "Select only columns you intend to modify."
        )
        if case_columns:
            add(
                "change_case",
                "User selected text case normalization.",
                columns=case_columns,
                case=selected_case,
            )

    with st.expander("Standardize dates"):
        date_columns = st.multiselect(
            "Date columns",
            columns,
            key=key("date_columns"),
        )
        date_formats = {
            "Choose the source format": None,
            "Day/month/year — 31/12/2026": "%d/%m/%Y",
            "Month/day/year — 12/31/2026": "%m/%d/%Y",
            "Year-month-day — 2026-12-31": "%Y-%m-%d",
            "Day-month-year — 31-12-2026": "%d-%m-%Y",
        }
        date_choice = st.selectbox(
            "Format currently used in those columns",
            list(date_formats),
            key=key("date_format"),
        )
        input_format = date_formats[date_choice]

        st.caption(
            "Output uses YYYY-MM-DD. Values that do not match "
            "the chosen format remain unchanged and are reported."
        )

        if date_columns and input_format:
            add(
                "normalize_dates",
                "User explicitly selected the source date format.",
                columns=date_columns,
                input_format=input_format,
            )
        elif date_columns:
            st.warning("Choose a source format to enable date conversion.")

    with st.expander("Remove duplicate rows"):
        remove_duplicates = st.checkbox(
            "Remove exact duplicate rows and keep the first",
            key=key("duplicates"),
        )
        st.caption(
            "Runs after the transformations above. Rows made "
            "identical by those transformations will also be removed."
        )
        if remove_duplicates:
            add(
                "remove_duplicates",
                "User approved deduplication after value transformations.",
            )

    with st.expander("Rename column headers"):
        enable_rename = st.checkbox(
            "Enable header renaming",
            key=key("rename_enabled"),
        )

        if enable_rename:
            st.caption(
                "All headers will have surrounding spaces removed. "
                "Edit the proposed names below."
            )
            mapping = {}
            for index, column in enumerate(columns):
                mapping[column] = st.text_input(
                    f"New name for {column!r}",
                    value=column.strip(),
                    key=key(f"rename_{index}"),
                ).strip()

            names = list(mapping.values())
            if any(not name for name in names):
                st.error("Column names cannot be empty.")
            elif len({name.casefold() for name in names}) != len(names):
                st.error("Column names must be unique, ignoring case.")
            elif any(old != new for old, new in mapping.items()):
                add(
                    "rename_columns",
                    "User approved the complete header mapping.",
                    mapping=mapping,
                )
        render_approved_plan(
        original=original,
        source_name=source_name,
        input_signature=input_signature,
        plan=plan,
    )


def render_approved_plan(
    original,
    source_name,
    input_signature,
    plan,
    namespace="manual",
):
    """Display, approve, execute, and export an already prepared plan."""
    source_token = hashlib.sha256(
        repr(input_signature).encode()
    ).hexdigest()[:16]

    def key(name):
        return f"{namespace}_{source_token}_{name}"
    
    # The displayed plan is the exact plan that execution will use.
    plan_json = json.dumps(plan, sort_keys=True, ensure_ascii=False)
    execution_token = hashlib.sha256(
        f"{source_token}:{plan_json}".encode()
    ).hexdigest()

    # Editing any executable operation invalidates previous results.
    result_key = f"{namespace}_cleaning_result"
    previous = st.session_state.get(result_key)
    if previous and previous["token"] != execution_token:
        st.session_state.pop(result_key, None)

    st.subheader("2. Review the execution plan")

    if not plan:
        st.info("Choose at least one valid operation above.")
        return

    for number, operation in enumerate(plan, start=1):
        st.write(
            f"**{number}. "
            f"{operation['operation'].replace('_', ' ').title()}**"
        )
        st.json(operation)

    # Approval must be renewed each time the plan changes.
    approval_key = key("approval")
    if st.session_state.get(key("approval_token")) != execution_token:
        st.session_state[approval_key] = False
        st.session_state[key("approval_token")] = execution_token

    approved = st.checkbox(
        "I approve the exact operations and order shown above.",
        key=approval_key,
    )

    if st.button(
        "Apply approved cleaning",
        disabled=not approved,
        key=key("apply"),
        type="primary",
    ):
        st.session_state.pop(result_key, None)

        try:
            with st.spinner("Cleaning and validating..."):
                cleaned, log = apply_plan(original, plan)
                validation = validate_result(
                    original, cleaned, plan, log
                )

                # The existing validator does not include failed dates
                # in unresolved_issues, so surface them from the log.
                for entry in log:
                    failed_rows = entry["details"].get("failed_rows", {})
                    for column, rows in failed_rows.items():
                        if rows:
                            validation["unresolved_issues"].append({
                                "type": "date_conversion_failed",
                                "column": column,
                                "count": len(rows),
                                "message": (
                                    f"{len(rows)} date value(s) in "
                                    f"{column!r} could not be converted. "
                                    f"Original values were preserved. "
                                    f"Original row indexes: {rows}"
                                ),
                            })

                exports = build_exports(
                    cleaned,
                    {
                        "log": log,
                        "validation": validation,
                        "original_rows": len(original),
                    },
                )

                st.session_state[result_key] = {
                    "token": execution_token,
                    "cleaned": cleaned,
                    "log": log,
                    "validation": validation,
                    "exports": exports,
                }

        except (ValueError, TypeError, KeyError) as exc:
            st.error(f"Cleaning could not finish: {exc}")
            st.info("Review the selected operations and try again.")
        except Exception:
            st.error(
                "An unexpected cleaning error occurred. "
                "No new result was published. Your original remains available."
            )

    result = st.session_state.get(result_key)
    if not result or result["token"] != execution_token:
        return

    st.subheader("3. Results and downloads")
    cleaned = result["cleaned"]
    validation = result["validation"]

    if validation["all_passed"]:
        st.success("Cleaning finished. Structural integrity checks passed.")
    else:
        st.error(
            "Integrity checks failed. Review the checks below. "
            "Cleaned CSV download is disabled."
        )

    st.caption(
        "Integrity checks do not guarantee that all data-quality "
        "problems are resolved."
    )

    metrics = st.columns(3)
    metrics[0].metric("Original rows", len(original))
    metrics[1].metric("Result rows", len(cleaned))
    metrics[2].metric("Rows removed", len(original) - len(cleaned))

    before, after = st.columns(2)
    with before:
        st.write("**Original — first 100 rows**")
        st.dataframe(original.head(100), use_container_width=True)
    with after:
        st.write("**Cleaned — first 100 rows**")
        st.dataframe(cleaned.head(100), use_container_width=True)

    st.caption(
        "Previews are independent. After duplicate removal, rows "
        "at the same displayed position may represent different records."
    )

    with st.expander("Integrity checks"):
        st.dataframe(
            pd.DataFrame(validation["checks"]),
            use_container_width=True,
        )

    issues = validation["unresolved_issues"]
    if issues:
        st.warning("Some issues remain:")
        for issue in issues:
            st.write(f"- {issue['message']}")
    else:
        st.info(
            "No remaining issues were reported by the current "
            "validator, which checks duplicates and outer whitespace."
        )

    with st.expander("Detailed change log"):
        st.json(result["log"])

    stem = Path(source_name).stem

    st.download_button(
        "Download cleaned CSV",
        data=result["exports"]["csv"],
        file_name=f"{stem}_cleaned.csv",
        mime="text/csv",
        disabled=not validation["all_passed"],
        key=key("download_csv"),
    )

    st.download_button(
        "Download change report",
        data=result["exports"]["report"],
        file_name=f"{stem}_change_report.txt",
        mime="text/plain",
        key=key("download_report"),
    )