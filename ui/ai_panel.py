import hashlib
import json

import streamlit as st

from agent.planner import generate_plan, validate_plan
from ingestion.profiler import inspect_column
from ui.cleaning_panel import render_approved_plan


DATE_FORMATS = {
    "Choose a format": None,
    "Day/month/year — 31/12/2026": "%d/%m/%Y",
    "Month/day/year — 12/31/2026": "%m/%d/%Y",
    "Year-month-day — 2026-12-31": "%Y-%m-%d",
    "Day-month-year — 31-12-2026": "%d-%m-%Y",
    "Month-day-year — 12-31-2026": "%m-%d-%Y",
    "Year/month/day — 2026/12/31": "%Y/%m/%d",
    "Day abbreviated-month year — 31 Dec 2026": "%d %b %Y",
}


def render_ai_panel(
    original,
    profile,
    source_name,
    input_signature,
    goal,
):
    st.header("AI cleaning planner")
    st.caption(
        "Groq receives your goal, column profiles and sample values, "
        "plus limited column details if requested. "
        "Cleaning runs locally only after your approval."
    )

    # A changed file, parsing option, or goal starts a fresh request.
    request_token = hashlib.sha256(
        repr((input_signature, goal)).encode()
    ).hexdigest()[:16]

    if st.session_state.get("ai_request_token") != request_token:
        st.session_state["ai_request_token"] = request_token
        st.session_state.pop("ai_bundle", None)
        st.session_state.pop("ai_cleaning_result", None)

    def key(name):
        return f"ai_request_{request_token}_{name}"

    if not goal.strip():
        st.info("Enter your cleaning goal above to begin.")
        return

    bundle = st.session_state.get("ai_bundle")
    questions = (
        bundle["plan"]["clarification_questions"]
        if bundle else []
    )

    if questions:
        st.subheader("The planner needs clarification")
        for question in questions:
            st.write(f"• {question['question']}")

    clarification = st.text_area(
        "Additional instructions or answers",
        placeholder=(
            "Answer any questions above, or add details such as "
            "which missing-value markers should become empty."
        ),
        key=key("clarification"),
    )

    confirmed_formats = {}

    with st.expander("Confirm source date formats"):
        st.caption(
            "If your goal includes date conversion, explicitly "
            "select the affected columns and their source formats."
        )

        date_columns = st.multiselect(
            "Columns whose date format you want to confirm",
            original.columns.tolist(),
            key=key("date_columns"),
        )

        for column in date_columns:
            choice = st.selectbox(
                f"Current date format in {column!r}",
                list(DATE_FORMATS),
                key=key(f"date_format_{column}"),
            )

            if DATE_FORMATS[choice] is not None:
                confirmed_formats[column] = DATE_FORMATS[choice]

    answers = {
        "additional_instructions": clarification.strip(),
        "date_formats": confirmed_formats,
    }
    answers_token = json.dumps(answers, sort_keys=True)

    # Changed answers make a previously generated plan stale.
    is_stale = (
        bundle is not None
        and bundle["answers_token"] != answers_token
    )

    if is_stale:
        st.session_state.pop("ai_cleaning_result", None)
        st.info(
            "Your answers changed. Generate an updated plan "
            "before approving or executing it."
        )

    consent = st.checkbox(
        "I agree to send this dataset's profile and limited "
        "sample values to Groq for planning.",
        key=key("consent"),
    )

    button_label = (
        "Generate updated plan" if bundle else "Generate cleaning plan"
    )

    if st.button(
        button_label,
        disabled=not consent,
        type="primary",
        key=key("generate"),
    ):
        # Clear previous output before requesting a replacement.
        st.session_state.pop("ai_bundle", None)
        st.session_state.pop("ai_cleaning_result", None)

        try:
            with st.spinner("The agent is inspecting and planning..."):
                plan = generate_plan(
                    goal=goal,
                    profile=profile,
                    inspect=lambda name: inspect_column(original, name),
                    answers=answers,
                )

            revision = st.session_state.get("ai_revision", 0) + 1
            st.session_state["ai_revision"] = revision
            st.session_state["ai_bundle"] = {
                "plan": plan,
                "answers_token": answers_token,
                "revision": revision,
            }
            st.rerun()

        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
            st.info("You can retry or switch to manual cleaning.")
            return
        except Exception:
            st.error(
                "The planner encountered an unexpected error. "
                "No cleaning was performed."
            )
            return

    bundle = st.session_state.get("ai_bundle")
    if bundle is None:
        return

    plan = bundle["plan"]

    for note in plan.get("notes", []):
        st.info(note)

    inspected = plan.get("inspected_columns", [])
    if inspected:
        st.caption("Columns inspected by the agent: " + ", ".join(inspected))

    if bundle["answers_token"] != answers_token:
        return

    if plan["clarification_questions"]:
        st.warning(
            "Answer the questions above and generate an updated plan. "
            "Cleaning is blocked until clarification is complete."
        )
        return

    if not consent:
        st.info("Enable the planning consent checkbox to continue.")
        return

    if not plan["operations"]:
        st.info(
            "The agent proposed no operations. Review its notes "
            "or make your goal more specific."
        )
        return

    # Revalidate the stored plan immediately before displaying approval.
    try:
        validated = validate_plan(
            {
                "action": "plan",
                "operations": plan["operations"],
                "clarification_questions": [],
                "notes": plan.get("notes", []),
            },
            original.columns.tolist(),
            answers,
        )
    except ValueError:
        st.error("The stored plan is invalid. Generate a new plan.")
        return

    render_approved_plan(
        original=original,
        source_name=source_name,
        input_signature=(
            input_signature,
            goal,
            answers_token,
            bundle["revision"],
        ),
        plan=validated["operations"],
        namespace="ai",
    )