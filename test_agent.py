import json
from unittest.mock import Mock

import pytest

import agent.planner as planner


@pytest.fixture
def profile():
    # Matches Member 2's column-profile structure.
    return {
        "columns": [
            {"name": "customer_name"},
            {"name": "email"},
            {"name": "registration_date"},
        ]
    }


def plan_response(operations=None, questions=None):
    return {
        "action": "plan",
        "operations": operations or [],
        "clarification_questions": questions or [],
        "notes": [],
    }


def trim_operation(column="customer_name"):
    return {
        "id": "op_001",
        "operation": "trim_whitespace",
        "reason": "Trim the requested column.",
        "columns": [column],
    }


@pytest.fixture(autouse=True)
def block_live_api(monkeypatch):
    """Never allow an accidental Groq request from these tests."""
    def blocked(*args, **kwargs):
        raise AssertionError("A test attempted a live API request.")

    monkeypatch.setattr(planner, "get_ai_response", blocked)


def test_valid_plan_preserves_selected_columns(monkeypatch, profile):
    expected = plan_response([
        trim_operation(),
        {
            "id": "op_002",
            "operation": "remove_duplicates",
            "reason": "Remove duplicates after trimming.",
        },
    ])

    mock_response = Mock(return_value=json.dumps(expected))
    monkeypatch.setattr(planner, "get_ai_response", mock_response)

    result = planner.generate_plan(
        "Trim customer_name and remove duplicates.",
        profile,
    )

    assert result["operations"] == expected["operations"]
    assert result["clarification_questions"] == []
    assert result["inspected_columns"] == []
    mock_response.assert_called_once()


def test_agent_can_request_column_inspection(monkeypatch, profile):
    mock_response = Mock(side_effect=[
        json.dumps({
            "action": "inspect",
            "columns": ["customer_name"],
        }),
        json.dumps(plan_response([trim_operation()])),
    ])
    monkeypatch.setattr(planner, "get_ai_response", mock_response)

    inspect = Mock(return_value={
        "name": "customer_name",
        "sample_values": [" Ali "],
    })

    result = planner.generate_plan(
        "Trim customer_name.",
        profile,
        inspect=inspect,
    )

    inspect.assert_called_once_with("customer_name")
    assert result["inspected_columns"] == ["customer_name"]

    second_request = json.loads(mock_response.call_args_list[1].args[1])
    assert (
        second_request["inspection_results"]["customer_name"]
        ["sample_values"] == [" Ali "]
    )


def test_clarification_returns_no_operations(monkeypatch, profile):
    expected = plan_response(questions=[{
        "id": "date_format",
        "question": "What is the source date format?",
    }])

    monkeypatch.setattr(
        planner,
        "get_ai_response",
        Mock(return_value=json.dumps(expected)),
    )

    result = planner.generate_plan(
        "Standardize registration_date.",
        profile,
    )

    assert result["operations"] == []
    assert len(result["clarification_questions"]) == 1


def test_unknown_column_is_rejected():
    payload = plan_response([trim_operation("nonexistent_column")])

    with pytest.raises(ValueError, match="unknown column"):
        planner.validate_plan(payload, ["customer_name"])


def test_date_conversion_requires_confirmation():
    payload = plan_response([{
        "id": "op_date",
        "operation": "normalize_dates",
        "reason": "Standardize confirmed dates.",
        "columns": ["registration_date"],
        "input_format": "%d/%m/%Y",
    }])

    with pytest.raises(ValueError, match="explicit confirmation"):
        planner.validate_plan(payload, ["registration_date"])

    result = planner.validate_plan(
        payload,
        ["registration_date"],
        answers={
            "date_formats": {
                "registration_date": "%d/%m/%Y",
            }
        },
    )

    assert result["operations"][0]["input_format"] == "%d/%m/%Y"


def test_questions_and_operations_cannot_coexist():
    payload = plan_response(
        operations=[trim_operation()],
        questions=[{
            "id": "scope",
            "question": "Which column should be changed?",
        }],
    )

    with pytest.raises(ValueError, match="resolve clarification"):
        planner.validate_plan(payload, ["customer_name"])


def test_invalid_json_stops_after_three_attempts(monkeypatch, profile):
    mock_response = Mock(return_value="not valid JSON")
    monkeypatch.setattr(planner, "get_ai_response", mock_response)

    with pytest.raises(ValueError, match="after three attempts"):
        planner.generate_plan("Trim customer_name.", profile)

    assert mock_response.call_count == 3


def test_empty_goal_does_not_call_api(profile):
    with pytest.raises(ValueError, match="Enter a cleaning goal"):
        planner.generate_plan("   ", profile)