# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- The gitleaks `mise` pin and `scan.yml`'s full-history checkout are now emitted
  only when the scanner layer is enabled; projects that enable `scan.yml` through
  another layer no longer carry the unused pin or an unbounded `fetch-depth`.
- The `[tool.ruff.lint.mccabe]` block is emitted only under the `all` ruleset,
  where `max-complexity` governs a selected rule (C901); the curated ruleset no
  longer renders it as dead config.

### Fixed

- `just fmt` runs `ruff check --fix` before `ruff format`, so its own output can
  no longer be rejected by `just fmt-check`.
- `just scan` scans committed history (`gitleaks git`) to match the CI gate,
  catching secrets that were committed and later deleted from the working tree.
- The mutation workflow no longer sets job-level `continue-on-error`, so genuine
  infrastructure failures surface instead of being masked; surviving mutants stay
  non-gating via `|| true` on the `mutmut` step.
- `.editorconfig` no longer forces 2-space indentation on `.toml`, which
  conflicted with the 4-space arrays in the generated `pyproject.toml`.
- The `ci` recipe comment no longer claims the local gate mirrors everything that
  blocks a PR; with scanners enabled it notes they run in CI only (`scan.yml`).

## [0.1.0] - 2026-06-25

### Added

- Initial Copier template scaffolding a fully-gated Python project: ruff (`select=ALL`
  or a curated allowlist), basedpyright (`recommended`), pytest with branch coverage, and
  a `just ci` gate that is green from the first commit.
- Pre-commit hooks wired to the same gates: ruff (lint + format) and hygiene fixers on
  commit, basedpyright and pytest on push, and a guard against unresolved `copier` `.rej`
  conflict files; hooks are installed automatically on initial `copier copy`.
- Independently toggleable guardrail layers: property tests (Hypothesis), mutation tests
  (mutmut), policy tests, scanners (Semgrep + gitleaks), dependency audit (pip-audit),
  Renovate config, and a SHA-pin policy (zizmor).
- `library` and `application` project types.
- License choices for generated projects: MIT, Apache-2.0, ISC, and proprietary.
- Selectable target Python version (3.11, 3.12, or 3.13), threaded through `requires-python`,
  ruff, basedpyright, mise, and the CI matrix.
- Tunable branch-coverage floor (`coverage_floor`), enforced by the coverage gate and, when
  enabled, the policy test.
- `copier update` support with a clean 3-way merge across template releases.

[Unreleased]: https://github.com/maybebyte/python-kickstarter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/maybebyte/python-kickstarter/releases/tag/v0.1.0
