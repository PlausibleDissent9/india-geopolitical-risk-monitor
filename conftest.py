# Root conftest: makes pytest put the repo root on sys.path regardless of
# how it is invoked (bare `pytest` vs `python -m pytest`), so tests can
# `from src import ...` in CI and locally alike.
