from hashlib import sha256
from pathlib import Path

import pandas as pd
import streamlit as st

from ingestion.loader import IngestionError, LoadOptions, load_csv
from ingestion.profiler import inspect_column, profile_csv


st.set_page_config(
    page_title="CSV Rescue",
    page_icon="🧹",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "sample_data" / "messy_customers.csv"


def clear_dataset_state():
    """Remove data and downstream results when the input changes."""
    for key in (
        "dataset",
        "metadata",
        "profile",
        "source_name",
        "plan",
        "approved_plan",
        "cleaned",
        "change_log",
        "validation",
        "exports",
        "goal",
        "inspection_column",
    ):
        st.session_state.pop(key, None)


st.title("CSV Rescue")
st.write(
    "Inspect messy CSV files, review data-quality issues, "
    "and prepare your cleaning workflow."
)

with st.sidebar:
    st.header("Load your data")

    source = st.radio(
        "Data source",
        ["Upload a CSV", "Use sample data"],
    )

    uploaded = None
    if source == "Upload a CSV":
        uploaded = st.file_uploader(
            "Choose a CSV file",
            type=["csv"],
            help="Up to 10 MB, 100,000 rows, and 200 columns.",
        )

    with st.expander("CSV reading options"):
        delimiter_label = st.selectbox(
            "Delimiter",
            ["Automatic", "Comma", "Semicolon", "Tab", "Pipe"],
        )
        encoding_label = st.selectbox(
            "Encoding",
            ["Automatic", "utf-8-sig", "utf-8",
             "utf-16", "cp1252", "latin-1"],
        )

    st.caption(
        "This screen does not call an AI service. "
        "Values are loaded as text to preserve leading zeros."
    )

delimiters = {
    "Automatic": None,
    "Comma": ",",
    "Semicolon": ";",
    "Tab": "\t",
    "Pipe": "|",
}

raw = None
source_name = None

if source == "Use sample data":
    if SAMPLE_PATH.is_file():
        raw = SAMPLE_PATH.read_bytes()
        source_name = SAMPLE_PATH.name
    else:
        st.error("The sample CSV is missing from sample_data.")
elif uploaded is not None:
    raw = uploaded.getvalue()
    source_name = uploaded.name

# Include parsing settings so changing them reloads the dataset.
signature = None
if raw is not None:
    signature = (
        sha256(raw).hexdigest(),
        source_name,
        delimiter_label,
        encoding_label,
    )

if signature != st.session_state.get("input_signature"):
    clear_dataset_state()
    st.session_state["input_signature"] = signature

if raw is None:
    st.info("Upload a CSV or select sample data to begin.")
    st.stop()

if "dataset" not in st.session_state:
    options = LoadOptions(
        delimiter=delimiters[delimiter_label],
        encoding=(
            None if encoding_label == "Automatic"
            else encoding_label
        ),
    )

    try:
        with st.spinner("Reading and inspecting your CSV..."):
            loaded = load_csv(raw, options)
            profile = profile_csv(loaded.dataset)

        # Save only after both loading and profiling succeed.
        st.session_state["dataset"] = loaded.dataset
        st.session_state["metadata"] = loaded.metadata
        st.session_state["profile"] = profile
        st.session_state["source_name"] = source_name

    except IngestionError as exc:
        st.error(exc.message)
        if exc.hint:
            st.info(exc.hint)
        st.stop()

    except Exception:
        st.error(
            "The file could not be profiled. Check the CSV "
            "format or try the sample dataset."
        )
        st.stop()

dataset = st.session_state["dataset"]
metadata = st.session_state["metadata"]
profile = st.session_state["profile"]

st.success(f"Loaded {st.session_state['source_name']}")

for warning in metadata.get("warnings", []):
    st.warning(warning)

metrics = st.columns(4)
metrics[0].metric("Rows", f"{profile['row_count']:,}")
metrics[1].metric("Columns", profile["column_count"])
metrics[2].metric(
    "Exact duplicate rows",
    profile["exact_duplicate_rows"],
)
metrics[3].metric(
    "Additional duplicates after trimming",
    profile["duplicates_after_trim"],
)

preview_tab, issues_tab, columns_tab = st.tabs(
    ["Data preview", "Findings", "Column inspector"]
)

with preview_tab:
    st.subheader("Original data")
    st.caption(
        "Showing the first 100 rows. Your original values "
        "have not been modified."
    )
    st.dataframe(dataset.head(100), use_container_width=True)

    with st.expander("File details"):
        st.json(metadata)

with issues_tab:
    st.subheader("Data-quality findings")
    st.caption(
        "Findings include possible issues and informational "
        "notices. Date and numeric patterns are suggestions, "
        "not confirmed data types."
    )

    if profile["issues"]:
        findings = pd.DataFrame(profile["issues"])
        st.dataframe(
            findings[["type", "column", "count", "detail"]],
            use_container_width=True,
        )
    else:
        st.success("No issues were detected by the current checks.")

    st.info(
        "Identifier-like columns should stay as text. "
        "Missing-value markers and date formats need review "
        "before any conversion."
    )

with columns_tab:
    selected_column = st.selectbox(
        "Choose a column",
        dataset.columns.tolist(),
        key="inspection_column",
    )

    details = inspect_column(dataset, selected_column)

    column_metrics = st.columns(3)
    column_metrics[0].metric(
        "Non-empty values", details["non_empty_count"]
    )
    column_metrics[1].metric(
        "Unique non-empty values", details["unique_count"]
    )
    column_metrics[2].metric(
        "Maximum text length", details["max_length"]
    )

    st.write("Most frequent non-empty values")
    st.dataframe(
        pd.DataFrame(
            details["top_values"],
            columns=["value", "count"],
        ),
        use_container_width=True,
    )

    with st.expander("Detailed column profile"):
        st.json(details["profile"])

st.subheader("What would you like to clean?")
st.text_area(
    "Describe your goal",
    placeholder=(
        "For example: trim customer names, remove duplicate "
        "rows, and standardize registration dates."
    ),
    key="goal",
)

st.caption(
    "Goal capture is ready. AI planning and approved cleaning "
    "will be connected in the next integration step."
)