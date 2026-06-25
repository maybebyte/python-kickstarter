# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-25

### Added

- Initial Copier template scaffolding a fully-gated Python project: ruff (`select=ALL`
  or a curated allowlist), basedpyright (`recommended`), pytest with branch coverage, and
  a `just ci` gate that is green from the first commit.
- Independently toggleable guardrail layers: property tests (Hypothesis), mutation tests
  (mutmut), policy tests, scanners (Semgrep + gitleaks), dependency audit (pip-audit),
  Renovate config, and a SHA-pin policy (zizmor).
- `library` and `application` project types.
- License choices for generated projects: MIT, Apache-2.0, ISC, and proprietary.
- `copier update` support with a clean 3-way merge across template releases.
