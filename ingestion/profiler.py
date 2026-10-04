"""Profiling and column inspection (Member 2).

profile_csv(dataset)        -> counts, per-column summaries, issue candidates
inspect_column(dataset, n)  -> statistics + limited sample values

Everything returned is plain dicts/lists/numbers so it is JSON-serialisable and can be
sent to the model (Member 3) or displayed (Member 1) without conversion.
Profiling NEVER modifies the dataset.
"""
from __future__ import annotations

import re

import pandas as pd

MAX_SAMPLES = 5
MISSING_MARKERS = {"na", "n/a", "null", "none", "nan", "-", "--", "?", "missing", "unknown", "undefined", "nil"}
ID_NAME_HINT = re.compile(r"(^|_|\b)(id|code|zip|postal|phone|mobile|sku|ssn|cnic|account)(_|\b|$)", re.I)

_ISO = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")
_TEXT_DATE = re.compile(r"^\d{1,2}[ \-](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[ \-,]+\d{4}$", re.I)
_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _non_empty(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    return s[s.str.strip().ne("")]


# ---------------------------------------------------------------- per-column detectors
def _whitespace(series: pd.Series) -> dict:
    s = series.astype("string")
    leading_trailing = int(s.ne(s.str.strip()).sum())
    inner = int(s.str.contains(r"\S {2,}\S|\t", regex=True).sum())
    return {"leading_trailing_cells": leading_trailing, "inner_multi_space_cells": inner}


def _missing(series: pd.Series) -> dict:
    s = series.astype("string")
    stripped = s.str.strip()
    empty = int(stripped.eq("").sum())
    markers: dict[str, int] = {}
    for val, cnt in stripped[stripped.str.lower().isin(MISSING_MARKERS)].value_counts().items():
        markers[str(val)] = int(cnt)
    return {"empty_cells": empty, "marker_counts": markers, "marker_cells": int(sum(markers.values()))}


def _looks_like_identifier(name: str, values: pd.Series) -> bool:
    if values.empty:
        return False
    v = values.str.strip()
    leading_zero = v.str.fullmatch(r"0\d+").mean() > 0.0 if len(v) else False
    name_hint = bool(ID_NAME_HINT.search(name))
    long_digits = v.str.fullmatch(r"\d{9,}").mean() > 0.5
    return bool(leading_zero or name_hint or long_digits)


def _date_candidate(values: pd.Series) -> dict | None:
    if values.empty:
        return None
    v = values.str.strip()
    iso = v.str.match(_ISO)
    num = v.str.match(_NUMERIC_DATE)
    text = v.str.match(_TEXT_DATE)
    matched = iso | num | text
    ratio = float(matched.mean())
    if ratio < 0.6:
        return None

    formats = []
    ambiguous = False
    if int(iso.sum()):
        formats.append("YYYY-MM-DD")
    if int(text.sum()):
        formats.append("D Mon YYYY")
    if int(num.sum()):
        parts = v[num].str.extract(_NUMERIC_DATE).astype(int)
        first_gt12 = bool((parts[0] > 12).any())
        second_gt12 = bool((parts[1] > 12).any())
        differ = bool((parts[0] != parts[1]).any())
        if first_gt12 and not second_gt12:
            formats.append("DD/MM/YYYY")
        elif second_gt12 and not first_gt12:
            formats.append("MM/DD/YYYY")
        elif first_gt12 and second_gt12:
            formats.append("MIXED (both day-first and month-first)")
        elif differ:
            formats.append("DD/MM/YYYY or MM/DD/YYYY")
            ambiguous = True
        else:
            formats.append("DD/MM/YYYY or MM/DD/YYYY")  # all day==month: harmless
    return {
        "match_ratio": round(ratio, 3),
        "formats_detected": formats,
        "ambiguous": ambiguous,
        "unparseable_examples": [str(x) for x in v[~matched].unique()[:3]],
        "unparseable_count": int((~matched).sum()),
    }


def _numeric_candidate(name: str, values: pd.Series, is_identifier: bool) -> dict | None:
    if values.empty or is_identifier:
        return None
    v = values.str.strip()
    cleaned = (
        v.str.replace(r"^[\$€£¥₨]\s*|\s*(PKR|USD|EUR|Rs\.?)$", "", regex=True)
        .str.replace("%", "", regex=False)
    )
    has_currency = bool((cleaned != v.str.replace("%", "", regex=False)).any())
    has_percent = bool(v.str.endswith("%").any())
    us = cleaned.str.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")
    eu = cleaned.str.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+(,\d+)?")
    plain = cleaned.str.fullmatch(_NUMBER.pattern)
    eu_decimal = cleaned.str.fullmatch(r"[+-]?\d+,\d{1,2}")
    ok = us | eu | plain | eu_decimal
    ratio = float(ok.mean())
    if ratio < 0.8:
        return None
    patterns = []
    if bool(plain.any()):
        patterns.append("plain")
    if bool(us.any()):
        patterns.append("thousands_comma")
    if bool(eu.any()) or bool(eu_decimal.any()):
        patterns.append("european_separators")
    return {
        "match_ratio": round(ratio, 3),
        "patterns": patterns,
        "has_currency_symbol": has_currency,
        "has_percent": has_percent,
        "separator_ambiguous": len(patterns) > 1 and "european_separators" in patterns,
        "non_numeric_examples": [str(x) for x in v[~ok].unique()[:3]],
    }


def _case_variants(values: pd.Series) -> int:
    """Number of distinct values that differ only by case / spacing from another value."""
    if values.empty:
        return 0
    grouped = values.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    uniq = pd.DataFrame({"raw": values.str.strip(), "norm": grouped}).drop_duplicates()
    return int((uniq.groupby("norm")["raw"].nunique() > 1).sum())


# ---------------------------------------------------------------- public API
def profile_column(df: pd.DataFrame, name: str) -> dict:
    series = df[name].astype("string")
    values = _non_empty(series)
    identifier = _looks_like_identifier(name, values)
    ws = _whitespace(series)
    miss = _missing(series)
    date = _date_candidate(values) if not identifier else None
    numeric = _numeric_candidate(name, values, identifier)
    variants = _case_variants(values)

    return {
        "name": name,
        "non_empty_count": int(len(values)),
        "unique_count": int(values.nunique()),
        "sample_values": [str(x) for x in values.drop_duplicates().head(MAX_SAMPLES)],
        "missing": miss,
        "whitespace": ws,
        "is_identifier_like": identifier,
        "date_candidate": date,
        "numeric_candidate": numeric,
        "case_variant_groups": variants,
    }


def profile_csv(dataset: pd.DataFrame) -> dict:
    """Contract: profile_csv(dataset) -> counts, column summaries, issue candidates."""
    dup_mask = dataset.duplicated(keep="first")
    dup_stripped = dataset.apply(lambda c: c.astype("string").str.strip()).duplicated(keep="first")
    columns = [profile_column(dataset, c) for c in dataset.columns]

    issues: list[dict] = []
    exact = int(dup_mask.sum())
    near = int((dup_stripped & ~dup_mask).sum())
    if exact:
        issues.append({"type": "exact_duplicate_rows", "column": None, "count": exact,
                       "detail": f"{exact} row(s) are exact copies of an earlier row."})
    if near:
        issues.append({"type": "duplicates_after_trim", "column": None, "count": near,
                       "detail": f"{near} more row(s) become duplicates once spaces are trimmed."})

    for c in columns:
        n = c["name"]
        ws = c["whitespace"]["leading_trailing_cells"]
        if ws:
            issues.append({"type": "whitespace", "column": n, "count": ws,
                           "detail": f"{ws} cell(s) have leading or trailing spaces."})
        if c["whitespace"]["inner_multi_space_cells"]:
            k = c["whitespace"]["inner_multi_space_cells"]
            issues.append({"type": "inner_whitespace", "column": n, "count": k,
                           "detail": f"{k} cell(s) have repeated spaces or tabs inside."})
        m = c["missing"]
        if m["marker_cells"]:
            issues.append({"type": "missing_markers", "column": n, "count": m["marker_cells"],
                           "detail": f"Placeholder missing values found: {m['marker_counts']}."})
        if m["empty_cells"]:
            issues.append({"type": "empty_cells", "column": n, "count": m["empty_cells"],
                           "detail": f"{m['empty_cells']} empty cell(s)."})
        d = c["date_candidate"]
        if d:
            detail = f"Looks like dates ({', '.join(d['formats_detected'])})."
            if d["ambiguous"]:
                detail += " Day/month order is ambiguous: ask the user before converting."
            if d["unparseable_count"]:
                detail += f" {d['unparseable_count']} value(s) do not look like dates, e.g. {d['unparseable_examples']}."
            issues.append({"type": "date_candidate", "column": n, "count": d["unparseable_count"],
                           "ambiguous": d["ambiguous"], "detail": detail})
        nu = c["numeric_candidate"]
        if nu and (nu["patterns"] != ["plain"] or nu["has_currency_symbol"] or nu["has_percent"]
                   or nu["non_numeric_examples"]):
            issues.append({"type": "numeric_candidate", "column": n, "count": len(nu["non_numeric_examples"]),
                           "detail": f"Looks numeric but has formatting: {nu['patterns']}"
                                     f"{', currency symbol' if nu['has_currency_symbol'] else ''}"
                                     f"{', percent' if nu['has_percent'] else ''}."})
        if c["is_identifier_like"]:
            issues.append({"type": "identifier_column", "column": n, "count": 0,
                           "detail": "Looks like an identifier (e.g. leading zeros). Do not convert to numbers."})
        if c["case_variant_groups"]:
            k = c["case_variant_groups"]
            issues.append({"type": "case_inconsistency", "column": n, "count": k,
                           "detail": f"{k} value group(s) differ only by upper/lower case or spacing."})

    return {
        "row_count": int(len(dataset)),
        "column_count": int(len(dataset.columns)),
        "exact_duplicate_rows": exact,
        "duplicates_after_trim": near,
        "columns": columns,
        "issues": issues,
    }


def inspect_column(dataset: pd.DataFrame, name: str, max_samples: int = 10) -> dict:
    """Contract: inspect_column(dataset, name) -> statistics + limited sample values."""
    if name not in dataset.columns:
        raise ValueError(f"Unknown column: {name!r}. Available: {list(dataset.columns)}")
    max_samples = max(1, min(int(max_samples), 25))  # hard cap: only limited data leaves the app
    series = dataset[name].astype("string")
    values = _non_empty(series)
    lengths = series.str.len()
    top = values.value_counts().head(max_samples)
    return {
        "name": name,
        "row_count": int(len(series)),
        "non_empty_count": int(len(values)),
        "unique_count": int(values.nunique()),
        "min_length": int(lengths.min()),
        "max_length": int(lengths.max()),
        "top_values": [{"value": str(k), "count": int(v)} for k, v in top.items()],
        "sample_values": [str(x) for x in values.drop_duplicates().head(max_samples)],
        "profile": profile_column(dataset, name),
    }
