# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Exclude Git control files from product inventories so linked worktrees and separate-git-dir sources prepare without copying administrative pointers.
- Keep mapped test paths literal through generated recipes and refuse unsupported parser syntax before tool execution.
- Preserve mapped initializer bytes and prepare all-new source/test declarations without supplying their payloads.
- Enroll complete isolated candidates in disposable Git indexes; retain and validate local reachable history/refs without changing source Git state, and reject unsupported Git context requirements.
- Serialize shared project metadata independently of task ownership, preserving pending-write recovery blockers.
- Validate each verification receipt's passing status and content-addressed identity before accepting it, including after destination checks.
- Refuse destination-check mutations and retain the intended payload, observed effects and recovery journal.
- Require a new receipt-bound host review when reconciliation changes candidate bytes or modes.
- Prepare declared static PEP 621 dependencies and default uv_build packages before freezing gates, including task-local locked environments and package assets.
- Validate retained inventories, baselines, environment and setup provenance on resumption.
- Preserve existing generated gate choices and coverage thresholds while freezing them against weakening.
- Pin Copier 9.15.2 and uv 0.13.4 as development-only integration-test prerequisites.
- Refresh the locked certifi and virtualenv development dependencies to their patched releases.

### Added

- JSON CLI and Python interface for task-owned prepare/resume, verification, reviewed return and explicit cleanup.
- Real pinned Copier generation, existing-project reuse, disposable promotion, complete product mappings and private external records.
- Helper-owned raw command results, real product test/branch-coverage evidence, candidate/mode/config/tool-bound receipts, and fail-closed stale/failed/interrupted evidence handling.
- Reviewed selective transfer with compatible three-way reconciliation, conflict protection, destination-layout checks and durable interrupted-return recovery.
- Maintained integration, safety and Hypothesis property tests replacing generated clamp examples; no runtime Python dependencies or live agent installation.
