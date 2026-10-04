"""CSV loading (Member 2).

Goals:
  * keep every value as the ORIGINAL string ("00123" stays "00123", "NA" stays "NA")
  * detect encoding and delimiter
  * enforce size limits
  * reject bad files with a readable message + a next step
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import BytesIO, StringIO

import pandas as pd

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 100_000
MAX_COLUMNS = 200
CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]
ENCODINGS_TO_TRY = ["utf-8-sig", "utf-16", "cp1252", "latin-1"]


class IngestionError(Exception):
    """Raised for any file we cannot load. `message` is safe to show to the user."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.hint = hint  # recoverable next step

    def __str__(self) -> str:
        return f"{self.message} {self.hint}".strip()


@dataclass
class LoadOptions:
    delimiter: str | None = None  # None = auto-detect
    encoding: str | None = None  # None = auto-detect
    max_bytes: int = MAX_BYTES
    max_rows: int = MAX_ROWS


@dataclass
class LoadResult:
    dataset: pd.DataFrame
    metadata: dict = field(default_factory=dict)


def _decode(raw: bytes, encoding: str | None) -> tuple[str, str]:
    if encoding:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            raise IngestionError(
                f"The file could not be read as {encoding}.",
                "Choose a different encoding or leave it on automatic.",
            )
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        order = ["utf-16"]
    else:
        order = [e for e in ENCODINGS_TO_TRY if e != "utf-16"]
    for enc in order:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise IngestionError(
        "The file encoding is not supported.",
        "Re-save the file as CSV UTF-8 and upload it again.",
    )


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS)).delimiter
    except csv.Error:
        first = text.splitlines()[0] if text.splitlines() else ""
        counts = {d: first.count(d) for d in CANDIDATE_DELIMITERS}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def check_headers(headers: list[str]) -> None:
    """Must run BEFORE pandas, because pandas silently renames duplicates (a, a -> a, a.1)."""
    if not headers or all(h.strip() == "" for h in headers):
        raise IngestionError("The first row has no column names.", "Add a header row and upload again.")
    blanks = [i + 1 for i, h in enumerate(headers) if h.strip() == ""]
    if blanks:
        raise IngestionError(
            f"Column(s) at position {blanks} have an empty header.",
            "Give every column a name and upload again.",
        )
    seen: dict[str, str] = {}
    dupes = []
    for h in headers:
        key = h.strip().lower()
        if key in seen:
            dupes.append(h)
        seen[key] = h
    if dupes:
        raise IngestionError(
            f"Duplicate column names found: {sorted(set(dupes))}.",
            "Rename the duplicate columns so each name is unique, then upload again.",
        )
    if len(headers) > MAX_COLUMNS:
        raise IngestionError(
            f"The file has {len(headers)} columns; the limit is {MAX_COLUMNS}.",
            "Remove unneeded columns and upload again.",
        )


def load_csv(raw: bytes, options: LoadOptions | None = None) -> LoadResult:
    """Contract: load_csv(bytes, options) -> Dataset plus parsing metadata."""
    options = options or LoadOptions()

    if not raw or not raw.strip():
        raise IngestionError("The file is empty.", "Upload a CSV that contains a header row and data.")
    if len(raw) > options.max_bytes:
        mb = options.max_bytes / (1024 * 1024)
        raise IngestionError(
            f"The file is {len(raw) / (1024 * 1024):.1f} MB; the limit is {mb:.0f} MB.",
            "Upload a smaller file or a sample of the rows.",
        )
    if b"\x00" in raw and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise IngestionError(
            "This does not look like a text CSV file (binary content found).",
            "Export the data as CSV from your spreadsheet program and try again.",
        )

    text, encoding = _decode(raw, options.encoding)
    text = text.lstrip("﻿")
    delimiter = options.delimiter or _detect_delimiter(text)

    try:
        headers = next(csv.reader(StringIO(text), delimiter=delimiter))
    except (StopIteration, csv.Error):
        raise IngestionError("Could not read a header row.", "Check the file is a valid CSV.")
    check_headers(headers)

    try:
        df = pd.read_csv(
            BytesIO(text.encode("utf-8")),
            sep=delimiter,
            encoding="utf-8",
            dtype="string",
            keep_default_na=False,
            na_filter=False,
            on_bad_lines="error",
            skip_blank_lines=True,
        )
    except pd.errors.EmptyDataError:
        raise IngestionError("The file has no data.", "Upload a CSV that contains rows.")
    except pd.errors.ParserError as exc:
        raise IngestionError(
            f"The file is malformed: {str(exc).splitlines()[0]}",
            "Check for rows with extra or missing delimiters or unclosed quotes, then upload again.",
        )

    if len(df) == 0:
        raise IngestionError("The file has a header but no data rows.", "Add data rows and upload again.")
    if len(df) > options.max_rows:
        raise IngestionError(
            f"The file has {len(df):,} rows; the limit is {options.max_rows:,}.",
            "Upload a smaller file or a sample of the rows.",
        )

    df.columns = [str(c) for c in df.columns]  # original header text, untouched
    warnings = []
    if encoding not in ("utf-8-sig", "utf-8"):
        warnings.append(f"File was read as {encoding}; check that accents and symbols look right.")
    if len(df.columns) == 1:
        warnings.append("Only one column was found. If you expected more, choose another delimiter.")

    return LoadResult(
        dataset=df,
        metadata={
            "encoding": encoding,
            "delimiter": delimiter,
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "column_names": list(df.columns),
            "size_bytes": len(raw),
            "warnings": warnings,
        },
    )
