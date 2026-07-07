set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# The complete local gate — every PR-blocking check, reproducible locally.
# Mirrors template/justfile.jinja's `ci` (audit is a member — the template chains it,
# and audit is itself a PR-blocking check here via the CI `scan` job's pip-audit step).
# `test` is the full generation matrix: give it a roomy TMPDIR (the default 4G tmpfs
# /tmp can overflow) — see "Run every gate" in AGENTS.md. Scanners stay CI-only (off `ci`).
ci: fmt-check lint typecheck test audit
    @echo "ci: all gates passed"

verify: ci

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

# one-time: sync the venv and install the git hooks (maintainer is not copier-generated)
setup:
    uv sync
    uv run pre-commit install

# run every hook over the whole tree: commit-stage hooks, then pre-push basedpyright
precommit:
    uv run pre-commit run --all-files
    uv run pre-commit run --all-files --hook-stage pre-push

# Out-of-band secret + SAST scan (semgrep + gitleaks); enforced in CI by the `scan` job, not `ci`.
scan:
    uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
    # `git` (not `dir`): scan committed history like CI, catching secrets committed then deleted.
    gitleaks git . --redact --exit-code 1

# Dependency vulnerability audit: pip-audit over the FULL locked graph.
# `--no-dev` is dropped (unlike the template): package=false puts every dep in the
# dev group, so the template's --no-dev would export 0 packages and pass vacuously.
# Chained into `just ci` (mirrors the template) and independently enforced in CI by the `scan` job's pip-audit step.
audit:
    uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
    uvx pip-audit@2.10.1 -r requirements-audit.txt
    rm -f requirements-audit.txt
