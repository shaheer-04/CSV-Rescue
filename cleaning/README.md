# Cleaning and reporting: how to use these modules

Owner: Member 4. Branch: feat/cleaning-reports.

## Data format

Load the CSV as text so values like 00123 are never changed:
pd.read_csv(BytesIO(raw), dtype="string", keep_default_na=False, na_filter=False)

## Supported operations

Every operation in a plan needs: id, operation, reason (plus the parameters below).
The engine rejects any other operation name.

| operation           | parameters                                  | what it does                                       |
|---------------------|---------------------------------------------|----------------------------------------------------|
| trim_whitespace     | columns (list)                              | removes leading and trailing spaces                |
| remove_duplicates   | none                                        | removes exact duplicate rows, keeps the first      |
| standardize_missing | columns (list), markers (list)              | turns markers like "NA" into empty values          |
| rename_columns      | mapping (dict of old name to new name)      | renames columns                                    |
| change_case         | columns (list), case ("lower"/"upper"/"title") | changes text case                               |
| normalize_dates     | columns (list), input_format (e.g. "%d/%m/%Y") | converts dates to YYYY-MM-DD                    |

Dates are never guessed. input_format is required, so the user must answer the
day-first or month-first question before this operation can run.
Values that fail conversion keep their original text and are listed in the report.

## Functions

apply_plan(original, approved_plan) in cleaning/engine.py
- Runs the operations in the given order on a copy. The original is never changed.
- Checks the whole plan first. If any step is invalid, nothing runs and a ValueError is raised.
- Returns (cleaned, log). The log has one entry per operation with:
  step, id, operation, reason, rows_before, rows_after, details.

validate_result(original, cleaned, plan, log) in reporting/validator.py
- Returns a dict: checks (name, passed, message), unresolved_issues, all_passed.

build_exports(cleaned, reports) in reporting/exporter.py
- reports is a dict: {"log": log, "validation": validation_result, "original_rows": number}
- Returns {"csv": bytes, "report": bytes}.

## Example files

Run: python -m reporting.make_fixtures
Files appear in reporting/fixtures/: original_example.csv, cleaned_example.csv,
change_report_example.txt, example_plan.json.