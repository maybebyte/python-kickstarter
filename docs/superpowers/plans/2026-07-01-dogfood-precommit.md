# Dogfood Pre-commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire pre-commit into the maintainer repo as a local-only gate that mirrors the guardrail the template ships, adapted to the maintainer's surface.

**Architecture:** Add `pre-commit` as a dev dependency, a root `.pre-commit-config.yaml` (hygiene hooks + local `uv run ruff`/`basedpyright` hooks + `forbid-rej`), `just setup`/`just precommit` recipes, and an AGENTS.md section. No CI job and no `test_generation.py` change — the substantive checks are already CI-enforced by the existing `lint`/`typecheck` jobs; hygiene is a local gate. Verification per task is running the relevant command and observing its output (there is no pytest surface for this layer).

**Tech Stack:** pre-commit (>=4,<5), uv, just, ruff (locked 0.15.19), basedpyright (1.39.8), `pre-commit/pre-commit-hooks` v6.0.0.

**Source spec:** `docs/superpowers/specs/2026-07-01-dogfood-precommit-design.md`

## Global Constraints

- Branch: work on `chore/dogfood-precommit` (already contains the spec commit `2cbacac`). Do not branch again.
- `pre-commit>=4,<5` — mirrors `minimum_pre_commit_version: "4.0.0"`.
- SHA-pin the `pre-commit-hooks` repo with its exact-tag comment: `rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c  # v6.0.0` (AGENTS.md NEVER rule: never change a pinned SHA without updating its exact-tag comment).
- Hygiene hooks (`end-of-file-fixer`, `trailing-whitespace`) carry `exclude: '^template/'` — `template/` is Jinja and its whitespace is deliberate (`keep_trailing_newline: true`).
- Local ruff hooks use `uv run ruff` (locked 0.15.19), NOT `astral-sh/ruff-pre-commit`.
- No pytest hook; no CI pre-commit job; no `test_generation.py` change; no CHANGELOG `[Unreleased]` entry (CHANGELOG is downstream/template-scoped).
- Commits: Conventional Commit format, no AI-attribution trailer, GPG-signed (automatic in this repo). Author is `Ashlen <dev@anthes.is>`.
- Every edited/added file outside `template/` must be hygiene-clean (no trailing whitespace, ends in a final newline) — the pre-commit hooks enforce this on the repo itself once installed.
- First `pre-commit run` downloads the `pre-commit-hooks` environment at the pinned SHA (needs network); subsequent runs are cached.

---

### Task 1: Add pre-commit dev dependency

**Files:**
- Modify: `pyproject.toml` (the `[dependency-groups] dev` array)
- Modify: `uv.lock` (regenerated)

**Interfaces:**
- Consumes: nothing.
- Produces: `uv run pre-commit` becomes available for all later tasks.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"pre-commit>=4,<5",` to the `[dependency-groups] dev` array, alongside the existing dev dependencies. Keep the array's existing ordering/style.

- [ ] **Step 2: Lock and sync**

Run: `uv lock && uv sync`
Expected: `uv.lock` updates to include `pre-commit` (and its deps: `cfgv`, `identify`, `nodeenv`, `virtualenv`, etc.); `uv sync` installs them into `.venv`.

- [ ] **Step 3: Verify pre-commit is runnable at the required major**

Run: `uv run pre-commit --version`
Expected: prints `pre-commit 4.x.y` (major 4).

- [ ] **Step 4: Verify the lock recorded pre-commit**

Run: `grep -A1 'name = "pre-commit"' uv.lock | head -2`
Expected: shows `name = "pre-commit"` and a `version = "4...."` line.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build(deps): add pre-commit dev dependency"
```

---

### Task 2: Add the root pre-commit config

**Files:**
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: `uv run pre-commit` (Task 1); `uv run ruff`, `uv run basedpyright` (already present).
- Produces: a validated pre-commit config that later recipes/tasks invoke.

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
minimum_pre_commit_version: "4.0.0"
default_install_hook_types: [pre-commit, pre-push]
default_stages: [pre-commit]

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c  # v6.0.0
    hooks:
      - id: check-merge-conflict
        args: [--assume-in-merge]
      - id: end-of-file-fixer
        exclude: '^template/'
      - id: trailing-whitespace
        exclude: '^template/'

  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check (--fix)
        entry: uv run ruff check --fix --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: basedpyright
        name: basedpyright (type check)
        entry: uv run basedpyright
        language: system
        types: [python]
        pass_filenames: false
        stages: [pre-push]
      - id: forbid-rej
        name: forbid copier .rej conflict files
        entry: "unresolved copier .rej conflict files present; resolve and delete them"
        language: fail
        files: '\.rej$'
```

- [ ] **Step 2: Validate the config parses**

Run: `uv run pre-commit validate-config .pre-commit-config.yaml`
Expected: no output, exit code 0 (invalid YAML/schema would print an error).

- [ ] **Step 3: Stage the new file so `--all-files` sees it, then run commit-stage hooks**

`--all-files` operates on `git ls-files`; an unstaged new file is invisible.

Run: `git add .pre-commit-config.yaml && uv run pre-commit run --all-files`
Expected: `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `ruff-check`, `ruff-format` each print `Passed` (the tree is already clean, so the fixer hooks make no changes and exit 0); `forbid-rej` prints `(no files to check) Skipped` — a `language: fail` hook only runs (and can only ever fail) when a matching `.rej` file is present. First run also prints `[INFO] Initializing environment...` lines while it fetches the pinned hooks repo.

- [ ] **Step 4: Run the pre-push stage hook**

Run: `uv run pre-commit run --all-files --hook-stage pre-push`
Expected: `end-of-file-fixer`, `trailing-whitespace`, and `basedpyright` all print `Passed` — the two fixers inherit a `pre-push` stage from the pinned pre-commit-hooks v6.0.0 manifest (which overrides `default_stages`), so they run here too. `check-merge-conflict`, `ruff-check`, `ruff-format`, and `forbid-rej` are stage-filtered out at pre-push.

- [ ] **Step 5: Confirm no files were modified**

Run: `git status --short`
Expected: only `A  .pre-commit-config.yaml` staged; no unexpected modifications from the fixer hooks.

- [ ] **Step 6: Prove `forbid-rej` has teeth (negative check)**

Every other step exercises only the green path; confirm the one un-CI-backstopped, repo-authored hook can actually fail.

Run: `printf 'x\n' > scratch.rej && uv run pre-commit run forbid-rej --files scratch.rej; rm -f scratch.rej`
Expected: `forbid-rej` reports `Failed` (non-zero) with the "unresolved copier .rej conflict files present" message, proving the gate has teeth. Use `--files scratch.rej`, NOT `git add -N` + `--all-files`: `*.rej` is gitignored, so an intent-to-add path would never feed the file to the hook and would give a false pass.

- [ ] **Step 7: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore(pre-commit): add local pre-commit config"
```

---

### Task 3: Add `just setup` and `just precommit` recipes

**Files:**
- Modify: `justfile`

**Interfaces:**
- Consumes: `.pre-commit-config.yaml` (Task 2).
- Produces: `just setup` (installs the git hooks) and `just precommit` (runs both hook stages).

- [ ] **Step 1: Add the recipes to `justfile`**

Add, after the existing `fmt-check` recipe:

```just

# one-time: sync the venv and install the git hooks (maintainer is not copier-generated)
setup:
    uv sync
    uv run pre-commit install

# run every hook over the whole tree: commit-stage hooks, then pre-push basedpyright
precommit:
    uv run pre-commit run --all-files
    uv run pre-commit run --all-files --hook-stage pre-push
```

- [ ] **Step 2: Verify the recipes are listed**

Run: `just --list`
Expected: `setup` and `precommit` appear among the recipes with their doc comments.

- [ ] **Step 3: Install the git hooks**

Run: `just setup`
Expected: `uv sync` reports up-to-date (or a no-op resolve); `pre-commit install` prints `pre-commit installed at .git/hooks/pre-commit` and `pre-commit installed at .git/hooks/pre-push`.

- [ ] **Step 4: Verify both git hooks were written**

Run: `test -f "$(git rev-parse --git-path hooks/pre-commit)" && test -f "$(git rev-parse --git-path hooks/pre-push)" && echo OK`
Expected: prints `OK` (both hook files exist).

Note: run this plan from a normal clone, not a linked git worktree — `just setup` inside a worktree installs the hooks into the shared common `.git/hooks/`, mutating the main checkout.

- [ ] **Step 5: Run the full local gate via the recipe**

Run: `just precommit`
Expected: line 1 (commit stage) shows `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `ruff-check`, `ruff-format` `Passed` and `forbid-rej` `(no files to check) Skipped`; line 2 (pre-push) shows `end-of-file-fixer`, `trailing-whitespace`, and `basedpyright` `Passed`; recipe exits 0.

- [ ] **Step 6: Commit**

Note: the git hooks are now installed, so this commit triggers the commit-stage hooks — they should pass on a clean tree (this is the dogfooding working).

```bash
git add justfile
git commit -m "chore: add just setup and precommit recipes"
```

---

### Task 4: Document pre-commit in AGENTS.md

**Files:**
- Modify: `AGENTS.md` (insert a new `## Pre-commit` section immediately after the "Lint & format this repo" section, before "Add a guardrail layer")

**Interfaces:**
- Consumes: the recipes (Task 3) and config (Task 2) that the section describes.
- Produces: nothing downstream.

- [ ] **Step 1: Insert the `## Pre-commit` section**

Insert immediately after the "Lint & format this repo" section's final paragraph and before `## Add a guardrail layer`:

````markdown
## Pre-commit

```bash
just setup      # one-time: sync the venv and install the git hooks
just precommit  # run every hook (commit-stage + pre-push basedpyright) over the whole tree
```

`pre-commit install` registers both git hooks (`default_install_hook_types: [pre-commit, pre-push]`). On commit: ruff-check `--fix`, ruff-format, end-of-file-fixer / trailing-whitespace (both `exclude: '^template/'` — template Jinja whitespace is deliberate), check-merge-conflict, forbid-rej. On push: end-of-file-fixer and trailing-whitespace also run (they inherit a `pre-push` stage from the pinned `pre-commit-hooks` manifest, on any changed non-`template/` text file), plus basedpyright when the push includes a `*.py` file.

This is a **local-only** gate: there is no pre-commit CI job, matching the template (whose downstream CI also never runs pre-commit). The ruff and basedpyright *substance* is enforced by the existing `lint` and `typecheck` CI jobs; the hygiene hooks (eof / trailing-whitespace / check-merge-conflict / forbid-rej) have **no** CI backstop and are a local convenience here. A bare `uv run pre-commit run --all-files` runs commit-stage hooks only — basedpyright fires on push or via `just typecheck`; `just precommit` runs both.

Deliberate divergences from `template/.pre-commit-config.yaml.jinja`: ruff runs via local `uv run ruff` hooks (locked 0.15.19) instead of the `astral-sh/ruff-pre-commit` repo (pinned 0.15.18) — the venv is always synced here, so there is no bootstrap reason to keep the isolated-env repo hook; the pytest hook is dropped (the maintainer's only suite is the heavy generation matrix — CI-only). The two configs share the SHA-pinned `pre-commit-hooks` block: **bump both `rev:` pins together** (v6.0.0 = `3e8a8703…`).
````

- [ ] **Step 2: Verify the section is present and placed correctly**

Run: `grep -nE '^## ' AGENTS.md`
Expected: `## Pre-commit` appears between `## Lint & format this repo` and `## Add a guardrail layer`.

- [ ] **Step 3: Verify AGENTS.md passes the hygiene hooks (it is not under template/, so it is checked)**

Run: `git add AGENTS.md && uv run pre-commit run --files AGENTS.md`
Expected: the three hygiene hooks (`trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict`) print `Passed`; `ruff-check`, `ruff-format`, and `forbid-rej` report `(no files to check) Skipped`; `basedpyright` does not appear (it is pre-push-only, while `--files` runs the commit stage).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): document pre-commit workflow"
```

---

### Task 5: Final acceptance

**Files:** none (verification only).

- [ ] **Step 1: Full gate green from a clean tree**

Run: `just precommit`
Expected: commit-stage line — five hooks `Passed` and `forbid-rej` `Skipped`; pre-push line — `end-of-file-fixer`, `trailing-whitespace`, `basedpyright` `Passed`; exit 0.

- [ ] **Step 2: Confirm working tree is clean (no hook left an unstaged fix)**

Run: `git status --short`
Expected: empty output.

- [ ] **Step 3: Confirm all commits are present on the branch**

Run: `git log --oneline main..HEAD`
Expected: six commits — the spec commit, the plan commit, and the four implementation commits (`build(deps)…`, `chore(pre-commit)…`, `chore: add just setup…`, `docs(agents)…`).

- [ ] **Step 4: Push and open the PR** (only when instructed by the operator)

Push the branch and open a PR with the pr-descriptions skill. The PR contains the spec, this plan, and the pre-commit wiring; note in the body that it is a local-only gate with no CI change, and reference gap #1 of the dogfooding audit. Also add a body line flagging the tracked follow-up: reconcile the template's shipped `ruff-pre-commit` v0.15.18 pin with the locked ruff 0.15.19 at the source (see the spec's Out-of-scope section).
