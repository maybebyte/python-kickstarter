set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# Run the template generation + update tests
test:
    uv run pytest

# Lint this repo's own tooling
lint:
    uv run ruff check .
