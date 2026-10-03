# Member 2 - Ingestion and Profiling
Files: ingestion/loader.py, ingestion/profiler.py, sample_data/messy_customers.csv, tests/test_ingestion.py

    from ingestion import load_csv, profile_csv, inspect_column, IngestionError
    result = load_csv(raw_bytes)          # result.dataset (all strings), result.metadata
    profile = profile_csv(result.dataset) # dict: counts, columns, issues
    info = inspect_column(result.dataset, "registration_date")

Run tests:  python -m pytest -q
