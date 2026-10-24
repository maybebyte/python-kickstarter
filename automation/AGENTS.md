# Agent contract — Kickstarter Workflow

`README.md` is the human entry point; this file is the agent contract.

## Hard rules

| Never | Instead |
| --- | --- |
| `# type: ignore` / `# noqa` to dodge a finding | fix the root cause |
| lower `coverage_floor` to pass | add tests; the policy test blocks a silent drop |
| `git commit --no-verify` | make the gate pass |
| weaken a test to make it green | fix the code under test |

## Start here

```bash
uv sync            # install deps + dev group
just               # list recipes
just ci            # the complete gate — must be green before pushing
```

## The gate

`just ci` is the COMPLETE fast gate: fmt-check, lint, typecheck, test+coverage, fuzz, policy, audit. Out-of-band: `just mutate` (mutation, non-gating); `just scan` (semgrep + gitleaks).

## Add a behavior test

Put it in `tests/unit/`. Test the contract, not internals; keep it deterministic. Use `tests/unit/test_cli.py` as a public-interface example.

## Add a property test

Put it in `tests/property/`. It MUST set `pytestmark = pytest.mark.property` and use `@given`. Runs via `just fuzz`. See `tests/property/test_workflow_properties.py` for public-interface properties with isolated example state.

## Mutation coverage

`just mutate`, then read survivors from `mutants/mutmut-cicd-stats.json`; kill them with `tests/unit/` cases. Non-gating by default.

## Lint and types

`just lint` / `just fmt` / `just typecheck`. Never inline-dodge a real finding.

## Dependencies

`uv add <pkg>` (runtime) or `uv add --dev <pkg>` (tooling). `uv.lock` is committed; CI runs `uv sync --locked`.

## Changelog

A PR that changes `src/` or `pyproject.toml` must add an entry under `## [Unreleased]` in `CHANGELOG.md`. Promote the entries under a version heading in each release commit.

## Meta-guardrail

Changing a gate (coverage floor, ruff select, type mode, Action pins) requires editing the matching test in `tests/policy/` in the SAME commit.
