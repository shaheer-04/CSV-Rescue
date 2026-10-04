import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.client import get_ai_response
from agent.prompts import SYSTEM_PROMPT


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Operation(StrictModel):
    id: str = Field(min_length=1)
    operation: Literal[
        "trim_whitespace",
        "remove_duplicates",
        "standardize_missing",
        "change_case",
        "normalize_dates",
        "rename_columns",
    ]
    reason: str = Field(min_length=1)

    columns: list[str] | None = None
    markers: list[str] | None = None
    case: Literal["lower", "upper", "title"] | None = None
    input_format: str | None = None
    mapping: dict[str, str] | None = None


class Question(StrictModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)


class PlanResponse(StrictModel):
    action: Literal["plan"]
    operations: list[Operation] = Field(max_length=20)
    clarification_questions: list[Question] = Field(max_length=10)
    notes: list[str] = Field(max_length=20)


class InspectionRequest(StrictModel):
    action: Literal["inspect"]
    columns: list[str] = Field(min_length=1, max_length=3)


REQUIRED_PARAMETERS = {
    "trim_whitespace": {"columns"},
    "remove_duplicates": set(),
    "standardize_missing": {"columns", "markers"},
    "change_case": {"columns", "case"},
    "normalize_dates": {"columns", "input_format"},
    "rename_columns": {"mapping"},
}

ALLOWED_DATE_FORMATS = {
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%d %b %Y",
}


def validate_plan(payload, column_names, answers=None):
    """Validate model output before it reaches the approval screen."""
    parsed = PlanResponse.model_validate(payload)
    result = parsed.model_dump(exclude_none=True)
    answers = answers or {}

    question_ids = [
        question["id"]
        for question in result["clarification_questions"]
    ]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("The planner returned duplicate question IDs.")

    if result["clarification_questions"] and result["operations"]:
        raise ValueError(
            "The planner must resolve clarification before proposing execution."
        )

    operation_ids = []
    known_columns = set(column_names)

    for index, operation in enumerate(result["operations"]):
        name = operation["operation"]
        operation_ids.append(operation["id"])

        supplied = set(operation) - {"id", "operation", "reason"}
        required = REQUIRED_PARAMETERS[name]

        if supplied != required:
            raise ValueError(
                f"{name} has missing or unexpected parameters."
            )

        if "columns" in required:
            selected = operation["columns"]

            if not selected or len(selected) != len(set(selected)):
                raise ValueError(
                    f"{name} needs a nonempty list of unique columns."
                )

            if not set(selected).issubset(known_columns):
                raise ValueError(
                    f"{name} references an unknown column."
                )

        if name == "standardize_missing":
            markers = operation["markers"]
            if not markers or any(not marker.strip() for marker in markers):
                raise ValueError("Missing-value markers cannot be empty.")

        if name == "normalize_dates":
            date_format = operation["input_format"]
            confirmed = answers.get("date_formats", {})

            if date_format not in ALLOWED_DATE_FORMATS:
                raise ValueError("The proposed date format is unsupported.")

            for column in operation["columns"]:
                if confirmed.get(column) != date_format:
                    raise ValueError(
                        f"Date format for {column!r} needs explicit confirmation."
                    )

        if name == "rename_columns":
            if index != len(result["operations"]) - 1:
                raise ValueError("Header renaming must be the last operation.")

            mapping = operation["mapping"]

            if set(mapping) != known_columns:
                raise ValueError(
                    "The rename plan must show every current column header."
                )

            names = list(mapping.values())
            if any(not value or value != value.strip() for value in names):
                raise ValueError("New headers must be nonempty and trimmed.")

            if len({value.casefold() for value in names}) != len(names):
                raise ValueError("Renaming would create duplicate headers.")

    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("The planner returned duplicate operation IDs.")

    return result


def generate_plan(goal: str, profile: dict, inspect=None, answers=None):
    """Investigate a profile and return a validated, unexecuted plan."""
    if not goal or not goal.strip():
        raise ValueError("Enter a cleaning goal first.")

    column_names = [
        column["name"] for column in profile.get("columns", [])
    ]
    if not column_names:
        raise ValueError("The dataset profile has no columns.")

    answers = answers or {}
    inspections = {}
    last_validation_error = None

    # At most three planning calls and three unique column inspections.
    for attempt in range(3):
        request = {
            "goal": goal.strip(),
            "profile": profile,
            "answers": answers,
            "inspection_results": inspections,
            "inspection_available": inspect is not None,
            "must_return_final_plan": attempt == 2,
            "previous_validation_error": last_validation_error,
        }

        response_text = get_ai_response(
            SYSTEM_PROMPT,
            json.dumps(request, ensure_ascii=False),
        )

        try:
            payload = json.loads(response_text)

            if not isinstance(payload, dict):
                raise ValueError("The response must be a JSON object.")

            if payload.get("action") == "inspect":
                requested = InspectionRequest.model_validate(payload)

                if attempt == 2:
                    raise ValueError("Inspection limit reached; return a plan.")

                if inspect is None:
                    raise ValueError("Column inspection is unavailable.")

                if not set(requested.columns).issubset(set(column_names)):
                    raise ValueError("Inspection references an unknown column.")

                new_columns = [
                    column for column in requested.columns
                    if column not in inspections
                ]

                if not new_columns:
                    raise ValueError(
                        "Those columns were already inspected; use their results."
                    )

                if len(inspections) + len(new_columns) > 3:
                    raise ValueError("At most three columns may be inspected.")

                for column in new_columns:
                    inspections[column] = inspect(column)

                last_validation_error = None
                continue

            result = validate_plan(payload, column_names, answers)
            result["inspected_columns"] = list(inspections)
            return result

        except (ValueError, TypeError, KeyError) as exc:
            last_validation_error = (
                f"Invalid response ({type(exc).__name__}). "
                "Check the exact schema, existing columns, required "
                "parameters, unique IDs, and date confirmations. "
                "If uncertain, return questions with no operations."
            )

    raise ValueError(
        "The planner could not produce a valid plan after three attempts. "
        "Try a simpler goal or use manual cleaning."
    )