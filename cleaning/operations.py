import pandas as pd


def trim_whitespace(original, columns):
    """Remove leading and trailing spaces from the chosen columns.

    Works on a copy, so the original data is never changed.
    Returns the cleaned data and a small summary of what changed.
    """
    unknown = set(columns) - set(original.columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")

    cleaned = original.copy(deep=True)
    changed_cells = 0

    for column in columns:
        before = cleaned[column].astype("string")
        after = before.str.strip()
        changed_cells += int(before.ne(after).fillna(False).sum())
        cleaned[column] = after

    return cleaned, {"changed_cells": changed_cells}








def remove_duplicates(original):
    """Remove rows that are exact copies of an earlier row.

    The first copy is kept. Works on a copy of the data.
    Returns the cleaned data and a summary, including which rows were removed.
    """
    cleaned = original.copy(deep=True)
    is_duplicate = cleaned.duplicated(keep="first")
    removed_rows = [int(i) for i in cleaned.index[is_duplicate]]

    cleaned = cleaned.loc[~is_duplicate]

    return cleaned, {
        "removed_rows": len(removed_rows),
        "removed_row_indexes": removed_rows,
    }






def standardize_missing(original, columns, markers):
    """Replace approved missing-value markers with a true empty value.

    Only the chosen columns are touched. Matching ignores extra spaces
    and upper/lower case. Works on a copy of the data.
    """
    unknown = set(columns) - set(original.columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")

    wanted = {m.strip().lower() for m in markers}
    cleaned = original.copy(deep=True)
    changed_cells = 0

    for column in columns:
        before = cleaned[column].astype("string")
        is_marker = before.str.strip().str.lower().isin(wanted).fillna(False)
        changed_cells += int(is_marker.sum())
        cleaned[column] = before.mask(is_marker, pd.NA)

    return cleaned, {"changed_cells": changed_cells}



def rename_columns(original, mapping):
    """Rename columns using a mapping of {old_name: new_name}.

    Rejects unknown columns, empty names, and names that would
    create duplicate columns. Works on a copy of the data.
    """
    unknown = set(mapping) - set(original.columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")

    new_names = [new.strip() for new in mapping.values()]
    if any(name == "" for name in new_names):
        raise ValueError("New column names cannot be empty.")

    final_names = [mapping.get(col, col).strip() for col in original.columns]
    if len(final_names) != len(set(final_names)):
        raise ValueError("Renaming would create duplicate column names.")

    cleaned = original.copy(deep=True)
    cleaned.columns = final_names

    renamed = {old: new.strip() for old, new in mapping.items() if old != new.strip()}
    return cleaned, {"renamed_columns": renamed}



def change_case(original, columns, case):
    """Change text case in the chosen columns.

    `case` must be "lower", "upper", or "title".
    Works on a copy of the data.
    """
    allowed = {"lower", "upper", "title"}
    if case not in allowed:
        raise ValueError(f"Unsupported case '{case}'. Use one of {sorted(allowed)}.")

    unknown = set(columns) - set(original.columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")

    cleaned = original.copy(deep=True)
    changed_cells = 0

    for column in columns:
        before = cleaned[column].astype("string")
        if case == "lower":
            after = before.str.lower()
        elif case == "upper":
            after = before.str.upper()
        else:
            after = before.str.title()
        changed_cells += int(before.ne(after).fillna(False).sum())
        cleaned[column] = after

    return cleaned, {"changed_cells": changed_cells, "case": case}


def normalize_dates(original, columns, input_format):
    """Convert dates in the chosen columns to YYYY-MM-DD.

    `input_format` is required (for example "%d/%m/%Y") because dates like
    03/04/2026 are ambiguous. Values that fail to convert are kept as they
    were and reported by row index. Empty and missing values are left alone.
    Works on a copy of the data.
    """
    unknown = set(columns) - set(original.columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")
    if not input_format.strip():
        raise ValueError("An input date format is required.")

    cleaned = original.copy(deep=True)
    changed_cells = 0
    failed_rows = {}

    for column in columns:
        values = cleaned[column].astype("string")
        text = values.str.strip()
        has_value = (text.notna() & text.ne("")).fillna(False).astype(bool)

        parsed = pd.to_datetime(
            text.where(has_value), format=input_format, errors="coerce"
        )
        valid = parsed.notna()
        failed = has_value & ~valid

        result = values.copy()
        result[valid] = parsed[valid].dt.strftime("%Y-%m-%d")

        changed_cells += int(result.ne(values).fillna(False).sum())
        failed_rows[column] = [int(i) for i in cleaned.index[failed]]
        cleaned[column] = result

    return cleaned, {
        "changed_cells": changed_cells,
        "input_format": input_format,
        "failed_rows": failed_rows,
    }