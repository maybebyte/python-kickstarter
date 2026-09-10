# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `enable_changelog` toggle (default `true`): ships a Keep-a-Changelog `CHANGELOG.md` and a
  PR-only `changelog.yml` check that fails when `src/` or `pyproject.toml` change without a
  `CHANGELOG.md` change; the `skip-changelog` label bypasses it. CI-only, no recipe.

## [0.2.0] - 2026-09-02

### Added

- `in_existing_repo` answer (default `false`): scaffold into a subdirectory of an
  existing git repository. Skips `git init` and the hook install, and omits the
  root-only files GitHub and Renovate read only at the repository root
  (`.github/workflows/*.yml`, `.pre-commit-config.yaml`, `renovate.json`), with an
  after-copy note listing what to recreate there. Copying into a subdirectory of a
  repository without it now aborts instead of silently creating a nested repository.

### Fixed

- The copy-time hook install no longer aborts (and rolls back) the whole copy when
  git's `core.hooksPath` is set; pre-commit refuses to install under it, so the task
  skips with a hint on stderr instead.
- The generated `.gitignore` ignores pytest-cov's `.coverage` data file alongside
  `coverage.xml`.

## [0.1.1] - 2026-08-04

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

[Unreleased]: https://github.com/maybebyte/python-kickstarter/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/maybebyte/python-kickstarter/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/maybebyte/python-kickstarter/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/maybebyte/python-kickstarter/releases/tag/v0.1.0
