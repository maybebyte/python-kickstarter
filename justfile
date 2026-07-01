set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# Run the template generation + update tests
test:
    uv run pytest

# Lint this repo's own tooling
lint:
    uv run ruff check .

# Type-check this repo's own tooling (the tests/ harness) under basedpyright recommended.
typecheck:
    uv run basedpyright

# Auto-format + apply safe lint fixes to this repo's own tooling (the tests/ harness).
# Lint-fix BEFORE format: ruff's fixes (import sort, SIM/UP/C4 rewrites) can emit
# unformatted code, so the formatter must run last or `fmt-check` may reject `fmt`'s output.
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# CI's format gate: fail if anything is unformatted.
fmt-check:
    uv run ruff format --check .
