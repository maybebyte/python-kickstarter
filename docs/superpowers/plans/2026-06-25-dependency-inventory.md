# Dependency-Surface Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every dependency surface — across both the maintainer harness and the generated project — discoverable and trustworthy, with an in-repo, test-asserted surface-map + `just deps` as the inventory of record, Renovate as the freshness/cross-check layer, and zizmor as the Actions pin-enforcement gate.

**Architecture:** Three roles, ordered by trustworthiness: (1) **inventory of record** = the in-repo surface-map in `AGENTS.md` + `just deps` (`uv tree --frozen`), version-controlled and asserted by generation tests; (2) **freshness + independent cross-check** = Renovate (a new *maintainer* `renovate.json`, scoped to avoid two desyncs; the template's shipped config verified, not changed); (3) **enforcement** = zizmor (already green in both layers, untouched). The work is purely additive — no `_migrations`, no `_template`-file additions.

**Tech Stack:** Copier 9.15.2 template (Jinja under `template/`), `just` recipes, `uv`/`uv.lock`, `mise` tool pins, GitHub Actions, pytest generation tests (`tests/`), basedpyright + ruff (`select=ALL`), Renovate JSON5/JSON config.

## Global Constraints

These apply to **every** task; each task's requirements implicitly include this section.

- **Source repo:** `/home/user/src/python-kickstarter`. Maintainer harness = repo root; generated project = `template/*.jinja`.
- **Single-source tool versions — never hardcode a version in a test.** Current pins (do not duplicate into assertions; anchor on stable text or use the existing parity test): zizmor `1.26.1`, semgrep `1.167.0`, pip-audit `2.10.1`, uv `0.11.23`, copier `9.15.2`, gitleaks `8.30.1`, just `1.50.0`, python `3.13`. `uvx copier@9.15.2` in the `deps-template` recipe must equal the `mise.toml` copier pin.
- **House test contract:** every gated row/clause is asserted **present-when-on AND absent-when-off**, anchored on a **named literal** (not a generic shape). Assert "unconditional" rows in the **MINIMAL (all-toggles-off) render too**, or over-gating won't be caught.
- **AGENTS.md NEVER rules** (`AGENTS.md` lines 65+): never add a file under `template/` without a generation-test assertion (this plan adds **no** new `template/` files — it modifies existing `.jinja` only); never bump an Action SHA without updating its exact-tag comment (this plan bumps **no** SHAs).
- **zizmor trust phrasing:** claim only **SHA-pinning** enforcement (`unpinned-uses`, always true under `--persona=regular`). Do **not** claim comment-drift (`ref-version-mismatch`) enforcement — unverified under `--persona=regular`.
- **Commits:** Conventional Commits (use the `commit-message-guide` skill). **No AI-attribution / `Co-Authored-By` trailer** (repo rule — see auto-memory `no-ai-attribution-trailer`). Keep **GPG signing enabled**. One commit per task unless a task says otherwise.
- **Running the full suite:** the full pytest matrix fills the 4 G tmpfs `/tmp`. Export `TMPDIR=$HOME/.cache` (same fs as the uv cache, ~108 G) before `just test` / full `uv run pytest` (see auto-memory `test-suite-disk-exhaustion`). Targeted single-test runs are fine without it.
- **Clean-tree precondition for `vcs_ref="HEAD"` renders (REQUIRED — read before Task 3).** Tasks 3/4/7 render the template at HEAD+worktree (the `render` fixture, `just deps-template`, and Task 7 Step 5's script). copier's dirty-HEAD path runs `git add -A` over the **whole real working tree** and then `git submodule update`; an **untracked nested git repo** (any path with a `.git` gitlink and no `.gitmodules` entry — e.g. `.claude/worktrees/…` created by `superpowers` worktree execution, the very execution method this plan mandates) makes the render abort with **exit 128** (`fatal: No url found for submodule path … in .gitmodules`), failing **every** render through the shared fixture. Before running any verification step: ensure `git status --porcelain` shows **no untracked nested `.git`** — add `.claude/` to `.gitignore` (or remove it) and clear any vendored nested repos/worktrees, or run from a clean checkout. Pristine CI checkouts (no `.claude/`) are unaffected, which is why the parity/roundtrip reasoning still holds there.
- **Test/lint/type commands:** `uv run pytest <path>` (targeted) or `just test` (full); `just typecheck` (basedpyright, `failOnWarnings`); `just lint` + `just fmt-check` (ruff `select=ALL` over `tests/`). New Python in `tests/` must pass all three.

## File map (what each task touches)

| File | Task | Change |
|---|---|---|
| `renovate.json` (NEW, repo root) | 1 | maintainer Renovate config, scoped (disable `uv` + `copier`, no `customManager`, no `pre-commit` manager) |
| *(GitHub repo settings — Renovate App)* | 2 | operator action: enable the Mend Renovate App on `maybebyte/python-kickstarter` |
| `tests/conftest.py` | 3 | add `vcs_ref="HEAD"` to the `render` fixture's `copier.run_copy` |
| `justfile` | 4 | add maintainer `deps` + `deps-template` recipes |
| `AGENTS.md` | 5 | new `## Inspect the dependency graph` section |
| `template/justfile.jinja` | 6 | add unconditional `deps:` recipe |
| `tests/test_generation.py` | 6, 7 | new present/absent + runtime assertions |
| `template/AGENTS.md.jinja` | 7 | extend `## Dependencies` with the surface-map |
| `CHANGELOG.md` | 8 | `[Unreleased] / ### Added` — template-side additions only |
| *(verification only)* `template/{% if enable_renovate %}renovate.json{% endif %}.jinja` | 9 | confirm coverage; change only if a gap is found (none expected) |

## Facts established during grounding (read before starting)

- **`v0.1.0` exists; HEAD is 23 commits ahead** (`git describe --tags` → `v0.1.0-23-g99672f1`). `copier copy`/`update` default to the **latest tag (v0.1.0)**, *not* HEAD — so the `render` fixture and the `deps-template` recipe **must** force `vcs_ref="HEAD"` / `--vcs-ref HEAD` to exercise in-development work. (The maintainer `AGENTS.md` "no tags until first release" note is now stale — leave it; the *guidance* still holds for future releases.)
- **`template/` and `copier.yml` are byte-identical to `v0.1.0`** (`git diff v0.1.0 HEAD -- template/ copier.yml` is empty). So flipping the `render` fixture to `vcs_ref="HEAD"` changes **no** existing render output on a clean tree — it only starts including the worktree once template work lands.
- **The fixture change is GPG-safe — but needs a clean working tree.** copier's dirty-HEAD path (`copier/_vcs.py:231–257`) clones the repo into a **temp dir**, then runs `git add -A` (work-tree pointed at the **real** tree) + `git commit --no-verify --no-gpg-sign` in the clone, then `git submodule update --init --recursive`. It **never writes** to the real repo's index/HEAD and is safe under Split GPG. ⚠️ It is **not** a pure no-op: `git add -A` sweeps the *entire* untracked tree into the temp commit, and any **untracked nested git repo** (e.g. `.claude/worktrees/…` from `superpowers` execution) makes the submodule step abort with **exit 128** — see the clean-tree precondition in **Global Constraints**. On a clean tree it merely emits `DirtyLocalWarning`.
- **`test_update_roundtrip.py` is unaffected** — it builds its own throwaway template repo and calls `copier.run_copy(..., vcs_ref="v0.1.0")` directly; it never uses the shared `render` fixture.
- **`deps-template` answers are valid:** `project_name` is the only no-default question; `package_name` defaults to `{{ project_name | lower | replace(' ','_') | replace('-','_') }}` → `deps_probe`; every other question has a default and every `enable_*` defaults to `true`. So `copier copy --defaults --data project_name="Deps Probe"` renders a valid, all-guardrails-on project.
- **No `enable_precommit` toggle exists** — `.pre-commit-config.yaml.jinja` ships unconditionally (the only precommit-named var is the hidden `enable_precommit_install`, which gates the copy-time hook-install task, not file presence).

---

### Task 1: Maintainer `renovate.json`

**Files:**
- Create: `renovate.json` (repo root)

**Interfaces:**
- Consumes: nothing.
- Produces: a maintainer Renovate config. No code depends on it; verified by `renovate-config-validator` (manual, one-time) and the no-desync reasoning below.

**Why scoped (do not "fix" these):** the config **omits a `customManager`** (its only `uvx` pin is `zizmor`, which must move in lockstep with the template — `test_generation.py:797` asserts maintainer `uvx zizmor@…` == rendered `scan.yml` zizmor pin; an independent bump would break that parity test) and **disables `uv` and `copier`**, the two multi-site pins with no parity test. `uv` is pinned in `mise.toml` (depName `uv`, `mise` manager) **and** in four `setup-uv version:` inputs in `test-template.yml` (depName `astral-sh/uv`, `github-actions` manager) — Renovate tracks **both** natively, but as *separate* deps they would bump in *separate* PRs and silently desync (no maintainer test asserts they agree), so both names are frozen and bumped by hand. `copier` is pinned in `mise.toml` **and** as `uvx copier@<ver>` in the Task 4 `justfile` recipe (untracked), so it is frozen too. Only `python`/`just` remain single-site in `mise.toml` and bump freely via the inherited `mise` manager; in-range `uv.lock` drift (ruff/pydantic-core/copier) is caught by `lockFileMaintenance`. The `pre-commit` manager is omitted (the harness has no pre-commit config of its own).

- [ ] **Step 1: Write `renovate.json`**

Create `renovate.json` with exactly this content:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "helpers:pinGitHubActionDigests"],
  "lockFileMaintenance": { "enabled": true, "schedule": ["before 4am on monday"] },
  "packageRules": [
    {
      "description": "uv is multi-site: pinned in mise.toml (Renovate depName 'uv', mise manager) AND in every setup-uv 'version:' input in test-template.yml (Renovate depName 'astral-sh/uv', github-actions manager). Renovate tracks BOTH natively, but they are separate deps that would bump in separate PRs with no maintainer test asserting the sites agree. Freeze BOTH names so uv is bumped manually across all sites in lockstep. (Alternative if you want automated freshness: drop enabled:false and add \"groupName\": \"uv\" so every uv site moves in one PR.)",
      "matchDepNames": ["uv", "astral-sh/uv"],
      "enabled": false
    },
    {
      "description": "copier becomes multi-site once Task 4's `just deps-template` lands: pinned in mise.toml (mise manager) AND as 'uvx copier@<ver>' in the justfile (untracked — no customManager). Renovate's mise manager would bump only mise.toml and silently desync the justfile pin, which Global Constraints require to match. Freeze so both copier sites are bumped manually together. (Alternative: keep mise auto-bumping copier and add a maintainer parity test asserting the justfile 'uvx copier@X.Y.Z' equals the mise.toml copier pin.)",
      "matchDepNames": ["copier"],
      "enabled": false
    }
  ]
}
```

- [ ] **Step 2: Validate the config (manual, one-time — needs a Node runtime)**

There is **no** standalone `renovate-config-validator` npm package; it ships inside `renovate`, and the validator auto-detects `renovate.json` in the cwd. Pin the version (not `@latest`) for reproducibility:

Run:
```bash
ver="$(npm view renovate version)"; echo "renovate $ver"
npx --yes --package "renovate@$ver" -- renovate-config-validator
```
Expected: `Config validated successfully` (or equivalent success line), exit 0.

Note: this is **not** a CI gate (like the template's own shipped `renovate.json`, it is unguarded in CI — an accepted tradeoff; a shared validator job could cover both later).

- [ ] **Step 3: Confirm no parity test is affected**

Run:
```bash
uv run pytest tests/test_generation.py::test_tool_version_pins_have_no_drift -v
```
Expected: PASS. (Sanity check — this test reads the *rendered* template, not the maintainer `renovate.json`, so it cannot be affected; running it documents that.)

- [ ] **Step 4: Commit**

```bash
git add renovate.json
git commit -m "build: add scoped maintainer renovate.json"
```

---

### Task 2: Enable the Renovate GitHub App (operator precondition)

**Files:** none — this is a **GitHub account action**, not a code change.

**Why it's a task:** committing `renovate.json` produces **zero** PRs, **zero** dashboard, and **zero** cross-check on its own. The Mend Renovate GitHub App (or a self-hosted runner) must be installed on `maybebyte/python-kickstarter` for Goal 1's freshness PRs + auto-detected `## Detected Dependencies` cross-check to appear. The in-repo record (surface-map + `just deps`) stands without it, so nothing is *hollow* if it's absent — only the freshness layer lapses.

- [ ] **Step 1: Check whether the app is already installed**

This requires the repo owner. Confirm at `https://github.com/maybebyte/python-kickstarter/settings/installations` (or `https://github.com/settings/installations`) whether **Renovate** is listed and has access to the repo.

> ⚠️ **Needs the user.** This touches the user's GitHub account/org and cannot be done from the working tree. Surface it to the user: "Is the Mend Renovate App installed on `maybebyte/python-kickstarter`? If not, install it from https://github.com/apps/renovate and grant access to that repo." Do not fabricate confirmation.

- [ ] **Step 2: If absent, install + grant access**

Install the Mend Renovate App (https://github.com/apps/renovate) and grant it access to `maybebyte/python-kickstarter`.

- [ ] **Step 3: Verify activation**

Expected (within a few minutes of install or first config push): a Renovate **onboarding PR** *or* a **Dependency Dashboard** issue appears on the repo. That issue's `## Detected Dependencies` section is the cross-check referenced by the surface-maps.

> **Operator acceptance (cost + trust).** Enabling Renovate means every dependency PR plus the weekly `lockFileMaintenance` triggers the full `test-template.yml` matrix (5 answer combos × 3 Pythons + lint + typecheck + zizmor) — a recurring CI cost worth bounding with a schedule + `prConcurrentLimit`/grouping. Installing the Mend App also grants a third-party GitHub App write access to a security-focused template repo; review its requested permission scope (or run a self-hosted Renovate runner) and record the decision before granting access.

> No commit — this task produces no repo change.

---

### Task 3: Pin the `render` fixture to `vcs_ref="HEAD"`

**Files:**
- Modify: `tests/conftest.py` (the `render` fixture's `copier.run_copy`, lines 100–108)

**Interfaces:**
- Consumes: nothing.
- Produces: a `render` fixture that renders **HEAD + dirty worktree**, so generation tests validate the in-development template (precondition for Tasks 6 & 7). The fixture signature/return type (`RenderFn = Callable[[Mapping[str, object], Path], Path]`) is unchanged.

**Why first (before template-side TDD):** new assertions for the `deps` recipe and surface-map would otherwise render `v0.1.0` (which predates them) and fail. With `vcs_ref="HEAD"`, copier folds in the dirty worktree (`git add -A` + `--no-gpg-sign --no-verify` wip-commit in a temp copy) — exactly what TDD on an untagged template needs.

- [ ] **Step 1: Add `vcs_ref="HEAD"` to the fixture's copier call**

In `tests/conftest.py`, the `_render` closure currently calls (lines 100–108):

```python
            _ = copier.run_copy(
                str(template_root),
                str(dst),
                data={"enable_precommit_install": False, **data},
                defaults=True,
                unsafe=True,
                overwrite=True,
                quiet=True,
            )
```

Change it to add `vcs_ref="HEAD"` and a comment explaining why:

```python
            # vcs_ref="HEAD" renders the in-development template (HEAD + dirty worktree),
            # not the latest SemVer tag copier defaults to (v0.1.0, 23+ commits behind).
            # copier captures the dirty tree via a temp-dir `git add -A` + a --no-gpg-sign
            # --no-verify wip-commit, so this is safe under Split GPG; it emits DirtyLocalWarning.
            _ = copier.run_copy(
                str(template_root),
                str(dst),
                data={"enable_precommit_install": False, **data},
                defaults=True,
                unsafe=True,
                overwrite=True,
                quiet=True,
                vcs_ref="HEAD",
            )
```

- [ ] **Step 2: Regression-check — existing generation tests still pass**

Because `template/` is byte-identical to `v0.1.0`, the rendered output is unchanged; only `DirtyLocalWarning` is now emitted per render.

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py -q
```
Expected: the same pass count as before the change (no failures, no errors). `DirtyLocalWarning` may appear in captured warnings — that is expected and acceptable.

- [ ] **Step 3: Confirm the roundtrip tests are unaffected**

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_update_roundtrip.py -q
```
Expected: PASS (these use their own `copier.run_copy(..., vcs_ref="v0.1.0")`, not the `render` fixture).

- [ ] **Step 4: Lint + typecheck the harness**

Run:
```bash
just lint && just fmt-check && just typecheck
```
Expected: clean (no new findings; the change is a single kwarg + comment).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py
git commit -m "test(generation): render HEAD+worktree in the render fixture"
```

---

### Task 4: Maintainer `deps` + `deps-template` recipes

**Files:**
- Modify: `justfile` (insert after the `typecheck` recipe, which ends at line 16, before the `fmt` doc-comment at line 18)

**Interfaces:**
- Consumes: the `mise.toml` copier pin (`copier = "9.15.2"`) — the recipe's `uvx copier@9.15.2` must match it.
- Produces: `just deps` (maintainer graph from the committed lock) and `just deps-template` (the in-development generated project's resolved graph). Standalone, on-demand; **not** wired into any aggregate gate (the maintainer repo has no `just ci`).

- [ ] **Step 1: Add both recipes to the maintainer `justfile`**

The maintainer `justfile` uses `set shell := ["bash", "-eu", "-o", "pipefail", "-c"]` (each plain recipe line runs as a separate `bash -c`). `deps` is a plain recipe; `deps-template` **must** be a shebang recipe so its `mktemp` dir survives across lines.

Insert between the `typecheck` recipe (ends line 16) and the `fmt` doc-comment (line 18):

```make
# Print the uv-resolved dependency graph from the committed lock (no resolve, no network).
deps:
    uv tree --frozen

# Inspect the in-development generated project's resolved graph: render HEAD/worktree with all
# guardrail toggles on into a throwaway dir, lock it, print the tree. `uvx copier@9.15.2` (not
# `uv run`) keeps this inspection from syncing/rewriting the maintainer's own lock/venv;
# unsetting the maintainer interpreter pin lets the explicit `uv lock` below resolve the
# rendered project's own 3.13 toolchain (else it inherits a leaked older/pinned UV_PYTHON and
# aborts); `--skip-tasks` drops every copy-time `_task` (git init, the heavy `uv sync`, the hook
# install) since we only need the lock for `uv tree`. Home-based TMPDIR keeps the throwaway on
# the same filesystem as the uv cache.
deps-template:
    #!/usr/bin/env bash
    set -euo pipefail
    unset VIRTUAL_ENV UV_PYTHON
    export UV_PYTHON_DOWNLOADS=automatic
    export TMPDIR="$HOME/.cache"
    mkdir -p "$TMPDIR"
    dir="$(mktemp -d)"
    trap 'rm -rf "$dir"' EXIT
    uvx copier@9.15.2 copy --trust --defaults --vcs-ref HEAD --skip-tasks \
        --data project_name="Deps Probe" \
        . "$dir"
    uv lock --directory "$dir"
    uv tree --frozen --directory "$dir"
```

- [ ] **Step 2: Run `just deps`**

Run:
```bash
just deps
```
Expected: exit 0; prints the maintainer project's `uv tree` (root package + its dev deps: copier, pytest, basedpyright, ruff, etc.) read from the committed `uv.lock`. No network, no `uv.lock` mutation — confirm `git status` shows `uv.lock` unchanged afterward.

> ⚠️ The maintainer `pyproject.toml` is `[tool.uv] package = false` with all tooling in `[dependency-groups]`. **Confirm `uv tree --frozen` actually lists the group tooling** (copier/pytest/basedpyright/ruff) and not just a bare root node. If it prints only the root, the recipe must include the groups — change the maintainer `deps` recipe to `uv tree --frozen --all-groups`. (Task 6's template `deps` recipe targets a normal package project and does **not** need this, so the two recipes may legitimately differ.)

- [ ] **Step 3: Run `just deps-template`**

Run:
```bash
just deps-template
```
Expected: exit 0; copier renders into a temp dir (a `DirtyLocalWarning` is normal if the worktree is dirty), `uv lock` resolves the rendered project's `>=3.13` graph, and `uv tree` prints it. The temp dir is removed on exit (the `trap`). Confirm the maintainer's own `uv.lock`/`.venv` are untouched (`git status` clean for them).

> If copier rejects `--data project_name="Deps Probe"` or any flag, do **not** silently change the design — the flags are verified (`--trust`/`--defaults`/`--vcs-ref`/`--skip-tasks`/`--data` are all valid copier 9.x CLI flags, and `--skip-tasks` requires `--trust`, which is present). A failure here is more likely a missing required answer; add the missing `--data key=value` and note it.

- [ ] **Step 4: Commit**

```bash
git add justfile
git commit -m "feat: add deps and deps-template inspection recipes"
```

---

### Task 5: Maintainer `AGENTS.md` surface-map

**Files:**
- Modify: `AGENTS.md` (insert a new `## Inspect the dependency graph` section after the "Lint & format" block, which ends at line 28, before `## Add a guardrail layer` at line 30)

**Interfaces:**
- Consumes: the `just deps` / `just deps-template` recipes from Task 4 (the map references them).
- Produces: the maintainer-side inventory of record (unconditional — no toggles in this repo). Verified by prose review + running the documented commands.

- [ ] **Step 1: Insert the surface-map section**

Add this section between line 28 (end of the Lint & format paragraph) and line 30 (`## Add a guardrail layer`):

````markdown
## Inspect the dependency graph

The inventory of record is this map + `just deps`. Renovate (`renovate.json`) keeps the
*tracked* surfaces fresh — `uv` (all sites) and `copier` are frozen and bumped by hand (see
the rows below) — and its Dependency Dashboard `## Detected Dependencies` section is an
independent cross-check.

| Surface | Pinned in | Read it with |
|---|---|---|
| uv / Python deps | `pyproject.toml`, `uv.lock` | `just deps` (`uv tree --frozen`); freshness `uv tree --outdated`; advisories — see below |
| uv & copier (CLIs, multi-site) | `mise.toml` `[tools]` **and** the four `setup-uv` `version:` inputs in `.github/workflows/test-template.yml` (uv); `mise.toml` **and** the `deps-template` recipe's `uvx copier@<ver>` (copier) | `grep -rn 'version:' .github/workflows` + read `mise.toml`; keep every site in lockstep (Renovate freezes both — bump by hand) |
| mise tools | `mise.toml` `[tools]` | read the file *(Renovate's `mise` manager tracks `python`/`just`; `uv` and `copier` are bump-manually — see the row above)* |
| GitHub Actions | `.github/workflows/*.yml` `uses:` (SHA + tag comment) | `grep -rn 'uses:' .github/workflows`; **trust:** the `zizmor` job enforces SHA pinning (`unpinned-uses`) |
| uvx tool pins | run-steps (`uvx <tool>@<ver>`) | `grep -rn 'uvx .*@' .github/workflows justfile` *(the `zizmor` pin is parity-locked to the template, and the `deps-template` recipe's `uvx copier@<ver>` must equal the `mise.toml` copier pin — bump each pair together)* |
| generated project's graph | rendered template | `just deps-template` |

*(No pre-commit surface here — the maintainer harness has none of its own; downstream projects
get one, mapped in the template's `## Dependencies`.)*

Advisories (the harness's deps are all dev, so **no** `--no-dev`; `pip-audit` is left unpinned —
a version baked into this markdown would be a tool pin no Renovate manager tracks):

```bash
uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt \
  && uvx pip-audit -r requirements-audit.txt \
  && rm -f requirements-audit.txt
```
````

- [ ] **Step 2: Run the documented advisory command (prove it works)**

Run:
```bash
uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt \
  && uvx pip-audit -r requirements-audit.txt \
  && rm -f requirements-audit.txt
```
Expected: exit 0; pip-audit reports on the maintainer's locked deps (no `requirements-audit.txt` left behind). If pip-audit reports an advisory, that's real signal — note it, do not suppress it.

- [ ] **Step 3: Prose review**

Re-read the section: every "Read it with" command is runnable from the repo root; the trust note says **SHA pinning** only (no comment-drift claim); the pre-commit caveat is accurate (the harness has no pre-commit config).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add dependency surface-map to maintainer AGENTS.md"
```

---

### Task 6: Template `justfile.jinja` `deps` recipe (+ generation & runtime tests)

**Files:**
- Modify: `template/justfile.jinja` (add an **unconditional** `deps:` in the ungated block — after `test:` at lines 25–26, before the first `{% if enable_property_tests %}` gate at line 27)
- Modify: `tests/test_generation.py` (new tests)

**Interfaces:**
- Consumes: the `render` fixture (now `vcs_ref="HEAD"`, Task 3), `run_in`, `MINIMAL`, `FULL`, `RenderFn` (all already importable in `test_generation.py`).
- Produces: a downstream `just deps` recipe. No later task depends on it.

- [ ] **Step 1: Write the failing generation test**

Add to `tests/test_generation.py`:

```python
def test_deps_recipe_ships_unconditionally(render: RenderFn, tmp_path: Path) -> None:
    """`just deps` is ungated — present in the all-off render and the all-on render."""
    minimal = render(MINIMAL, tmp_path / "min")
    jf_min = (minimal / "justfile").read_text()
    assert "\ndeps:\n" in jf_min
    assert "uv tree --frozen" in jf_min

    full = render(FULL, tmp_path / "full")
    assert "uv tree --frozen" in (full / "justfile").read_text()
```

- [ ] **Step 2: Run it — verify it fails**

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py::test_deps_recipe_ships_unconditionally -v
```
Expected: FAIL on `assert "\ndeps:\n" in jf_min` (no `deps:` recipe rendered yet).

- [ ] **Step 3: Add the unconditional `deps:` recipe to the template**

In `template/justfile.jinja`, the `test:` recipe is at lines 25–26 and the first gate (`{% if enable_property_tests %}`) is at line 27. Insert the recipe between them:

```jinja
test:
    uv run pytest -m "not property" tests/unit

# Print the resolved dependency graph from the committed lock (no resolve, no network).
deps:
    uv tree --frozen
{% if enable_property_tests %}
```

(The `{% if enable_property_tests %}` line shown is the existing line 27 — do not duplicate it; the new three lines go immediately above it.)

- [ ] **Step 4: Run the generation test — verify it passes**

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py::test_deps_recipe_ships_unconditionally -v
```
Expected: PASS.

- [ ] **Step 5: Write the failing runtime test**

Add to `tests/test_generation.py`:

```python
def test_deps_recipe_runs(render: RenderFn, tmp_path: Path) -> None:
    """The rendered `just deps` exits clean against the committed lock."""
    project = render(MINIMAL, tmp_path / "out")
    result = run_in(project, "just", "deps")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip(), "uv tree printed nothing"
```

- [ ] **Step 6: Run the runtime test — verify it passes**

The render fixture's copy-time `_tasks` (`uv lock`, `uv sync`) create `uv.lock`, so `uv tree --frozen` reads it.

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py::test_deps_recipe_runs -v
```
Expected: PASS. (If it errors with "tool not found", the fixture would have failed closed earlier — ensure `just`/`uv` are on PATH.)

- [ ] **Step 7: Lint + typecheck the new tests**

Run:
```bash
just lint && just fmt-check && just typecheck
```
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add template/justfile.jinja tests/test_generation.py
git commit -m "feat(template): add unconditional just deps recipe"
```

---

### Task 7: Template `AGENTS.md.jinja` dependency surface-map (+ toggle-correct assertions)

**Files:**
- Modify: `template/AGENTS.md.jinja` (extend the `## Dependencies` section — insert after the prose at line 44, before `{% if enable_policy_tests %}` at line 45)
- Modify: `tests/test_generation.py` (a section-extractor helper + six present/absent tests)

**Interfaces:**
- Consumes: the `render` fixture (`vcs_ref="HEAD"`), `MINIMAL`, `FULL`, `RenderFn`.
- Produces: the toggle-gated downstream surface-map. No later task depends on it.

**TDD note:** the surface-map is one cohesive Jinja block with interdependent conditional rows; building it row-by-row via successive table edits is fragile. So this task writes the **whole failing test suite first**, watches it fail, implements the complete block once, then watches it pass — test-first at the task level. Markdown-table whitespace under Jinja is finicky, so Step 5 renders and **visually verifies** the table before the assertions are trusted.

**Gating contract (verified against the actual toggles):**

| Row / clause | Gate |
|---|---|
| `### Inspect the dependency graph` heading; uv/Python row; mise row; pre-commit row; GitHub Actions row | unconditional |
| `uv_build` build-backend row | `project_type == "library"` (applications render no `[build-system]`) |
| zizmor SHA-pinning trust clause (in the Actions row) | `enable_sha_pin_policy` |
| scanner-pins row (`semgrep` + `gitleaks`) | `enable_scanners` |
| advisories note (`just audit` / pip-audit) | `enable_dependency_audit` |
| Renovate lead sentence + every "Renovate … tracks …" parenthetical | `enable_renovate` (fallback lead when off) |

- [ ] **Step 1: Add the section-extractor helper to the test file**

Add near the top of `tests/test_generation.py` (after the imports / constants):

```python
def _deps_section(project: Path) -> str:
    """The rendered AGENTS.md `## Dependencies` section text, up to the next `## ` heading."""
    text = (project / "AGENTS.md").read_text()
    after = text.split("## Dependencies", 1)[1]
    return after.split("\n## ", 1)[0]
```

(`Path` is import-guarded under `TYPE_CHECKING`, **but** `test_generation.py` starts with `from __future__ import annotations`, so the annotation is never evaluated at runtime — use the **bare** `Path`, matching every other signature in the file. Do **not** quote it as `"Path"`: a quoted annotation trips ruff `UP037` and fails `just lint` (the `lint` CI gate).)

- [ ] **Step 2: Write all six failing tests**

Add to `tests/test_generation.py`:

```python
def test_surface_map_unconditional_rows(render: RenderFn, tmp_path: Path) -> None:
    """Heading + always-present rows render even in the all-off (MINIMAL) tree."""
    for name, answers in (("min", MINIMAL), ("full", FULL)):
        section = _deps_section(render(answers, tmp_path / name))
        assert "### Inspect the dependency graph" in section
        assert "| mise tools |" in section
        assert "pre-commit hooks" in section
        assert "GitHub Actions" in section
        assert "setup-uv" in section  # the unconditional uv-CLI multi-site row


def test_surface_map_scanner_row_toggles(render: RenderFn, tmp_path: Path) -> None:
    on = _deps_section(render({**MINIMAL, "enable_scanners": True}, tmp_path / "on"))
    assert "semgrep" in on
    assert "gitleaks" in on
    off = _deps_section(render(MINIMAL, tmp_path / "off"))
    assert "semgrep" not in off


def test_surface_map_advisories_toggle(render: RenderFn, tmp_path: Path) -> None:
    on = _deps_section(render({**MINIMAL, "enable_dependency_audit": True}, tmp_path / "on"))
    assert "pip-audit" in on
    off = _deps_section(render(MINIMAL, tmp_path / "off"))
    assert "pip-audit" not in off


def test_surface_map_uv_build_row_is_library_only(render: RenderFn, tmp_path: Path) -> None:
    lib = _deps_section(render(MINIMAL, tmp_path / "lib"))  # MINIMAL is a library
    assert "uv_build" in lib
    app = _deps_section(render({**MINIMAL, "project_type": "application"}, tmp_path / "app"))
    assert "uv_build" not in app


def test_surface_map_zizmor_trust_note_toggles(render: RenderFn, tmp_path: Path) -> None:
    on = _deps_section(render({**MINIMAL, "enable_sha_pin_policy": True}, tmp_path / "on"))
    assert "unpinned-uses" in on
    # Render the off-case with another toggle on so the section still has gated content.
    off = _deps_section(
        render(
            {**MINIMAL, "enable_sha_pin_policy": False, "enable_scanners": True},
            tmp_path / "off",
        )
    )
    assert "semgrep" in off  # section really rendered with content
    assert "unpinned-uses" not in off


def test_surface_map_renovate_mentions_toggle(render: RenderFn, tmp_path: Path) -> None:
    on = _deps_section(render({**MINIMAL, "enable_renovate": True}, tmp_path / "on"))
    assert "Renovate" in on
    off = _deps_section(render(MINIMAL, tmp_path / "off"))
    assert "Renovate" not in off  # whole word absent from the section when off
```

- [ ] **Step 3: Run the six tests — verify they all fail**

Run:
```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py -k surface_map -v
```
Expected: all six FAIL (the surface-map doesn't exist yet — `### Inspect the dependency graph` is absent, so `_deps_section` returns only the existing one-line prose).

- [ ] **Step 4: Implement the surface-map in `template/AGENTS.md.jinja`**

In `template/AGENTS.md.jinja`, the `## Dependencies` section is lines 42–44; line 45 is `{% if enable_policy_tests %}`. Insert the block **after** line 44 and **before** line 45. The existing context is:

```jinja
## Dependencies

`uv add <pkg>` (runtime) or `uv add --dev <pkg>` (tooling). `uv.lock` is committed; CI runs `uv sync --locked`.
{% if enable_policy_tests %}
```

Change it to (insert the new content between the prose line and the `{% if enable_policy_tests %}`):

```jinja
## Dependencies

`uv add <pkg>` (runtime) or `uv add --dev <pkg>` (tooling). `uv.lock` is committed; CI runs `uv sync --locked`.

### Inspect the dependency graph

{% if enable_renovate %}The inventory of record is this map + `just deps`. Renovate (`renovate.json`) keeps every surface fresh, and its Dependency Dashboard `## Detected Dependencies` section is an independent cross-check.{% else %}The inventory of record is this map + `just deps` — each row names the one command that reads its surface.{% endif %}

| Surface | Pinned in | Read it with |
|---|---|---|
| uv / Python deps | `pyproject.toml`, `uv.lock` | `just deps` (`uv tree --frozen`) |
{% if project_type == "library" %}| build backend | `[build-system].requires` (`uv_build` floor) | read `pyproject.toml`{% if enable_renovate %} *(Renovate's `pep621` manager tracks it)*{% endif %} |
{% endif %}| uv (CLI) | `mise.toml` **and** the `setup-uv` `version:` inputs in `.github/workflows/*.yml` | `grep -rn 'version:' .github/workflows` — keep every `version:` input and the `mise.toml` `uv` pin in lockstep |
| mise tools | `mise.toml` `[tools]` | read the file{% if enable_renovate %} *(Renovate's `mise` manager tracks them)*{% endif %} |
| pre-commit hooks | `.pre-commit-config.yaml` `rev:` | read the file{% if enable_renovate %} *(Renovate's `pre-commit` manager tracks them)*{% endif %} |
| GitHub Actions | `.github/workflows/*.yml` `uses:` (SHA + tag comment) | `grep -rn 'uses:' .github/workflows`{% if enable_sha_pin_policy %}; **trust:** the `zizmor` step enforces SHA pinning (`unpinned-uses`){% endif %} |
{% if enable_scanners %}| scanner tool pins | `uvx semgrep@…` (run-steps); `gitleaks` (`mise.toml`) | `grep -rn 'uvx .*@' .github/workflows justfile` for semgrep; read `mise.toml` for gitleaks{% if enable_renovate %} *(Renovate's regex `customManager` tracks the `uvx` pins; `gitleaks` via the `mise` manager)*{% endif %} |
{% endif %}{% if enable_dependency_audit %}
Advisories: `just audit` (pip-audit over the locked runtime deps).
{% endif -%}
{% if enable_policy_tests %}
```

(Again, the trailing `{% if enable_policy_tests %}` is the existing line 45 — shown for placement; do not duplicate it.)

> **Two whitespace fixes are load-bearing here** (copier renders with `trim_blocks=False`, `lstrip_blocks=False`, `keep_trailing_newline=True` — only `keep_trailing_newline` is set in `copier.yml` `_envops`; the rest are Jinja defaults). (1) The advisories block closes with **`{% endif -%}`** (note the `-`): without the trim, a `enable_policy_tests=off` render (the default MINIMAL config) leaves a trailing blank line, so the rendered `AGENTS.md` ends in `\n\n` — which the downstream `end-of-file-fixer` pre-commit hook rewrites, breaking the existing `test_precommit_config_valid` **and** every generated policy-off project's first `pre-commit run`. The same `-%}` also removes the extra blank line before `## Meta-guardrail` whenever `enable_policy_tests` is on. (2) The `uv (CLI)` row is **unconditional** (Renovate tracks it via `config:recommended`, but the map must still name it because the `uv` binary is pinned in `mise.toml` *and* the `setup-uv version:` inputs — the most drift-prone surface). Step 5 verifies both empirically.

- [ ] **Step 5: Render the toggle matrix and verify table shape, EOF bytes, and the newline budget**

Markdown tables are whitespace-sensitive under Jinja, and a trailing blank line breaks the downstream `end-of-file-fixer` hook. Check **three** things, not just table shape: (1) every table well-formed; (2) the rendered `AGENTS.md` ends in exactly one `\n` (a trailing `\n\n` fails Step 6's `test_precommit_config_valid`); (3) the AGENTS.md newline budget (`test_agent_contract` asserts `< 80`) is not breached on the **largest** (FULL) render. This run also covers the two combos the per-test cases don't — `scanners-off+audit-on` and `renovate-off`:

```bash
TMPDIR=$HOME/.cache uv run python - <<'PY'
from pathlib import Path
import tempfile, copier
from tests.test_generation import MINIMAL, FULL, _deps_section
from tests.conftest import without_interpreter_pins
cases = {
    "FULL": FULL,
    "MINIMAL": MINIMAL,
    "APP": {**MINIMAL, "project_type": "application"},
    "SCAN_OFF_AUDIT_ON": {**MINIMAL, "enable_scanners": False, "enable_dependency_audit": True},
    "RENOVATE_OFF": {**FULL, "enable_renovate": False},
}
for name, data in cases.items():
    d = Path(tempfile.mkdtemp())
    with without_interpreter_pins():
        copier.run_copy(".", str(d), data={"enable_precommit_install": False, **data},
                        defaults=True, unsafe=True, overwrite=True, quiet=True, vcs_ref="HEAD")
    raw = (d / "AGENTS.md").read_bytes()
    nlines = raw.count(b"\n")
    ends_dbl = raw.endswith(b"\n\n")
    print(f"\n===== {name}  (newlines={nlines}, ends_dblnl={ends_dbl}) =====")
    print(_deps_section(d))
PY
```
Expected: every table well-formed (one row per line, no stray blank line splitting it); **`ends_dblnl=False` for every case** (especially MINIMAL/APP, where policy is off and the section is the file tail); **`newlines` < 80 for FULL** (the largest render). FULL shows all rows + Renovate parentheticals + advisories; MINIMAL shows the unconditional rows (incl. the `uv (CLI)` row) + the build-backend row (library) + the fallback lead, with **no** "Renovate"/"semgrep"/"pip-audit"/"unpinned-uses"; APP omits the `uv_build` build-backend row. If a row is malformed or `ends_dblnl=True`, the `{% endif -%}` trim after the advisories block (Step 4) is what keeps a policy-off render to a single trailing newline — fix it and re-run.

- [ ] **Step 6: Run the six tests + the whole-tree-hook gate tests — verify they all pass**

The six `surface_map` tests assert only substring presence/absence and **cannot** see a trailing-blank/EOF regression in the rendered `AGENTS.md`. Also run the existing rendered-project gate tests that stage the tree and run `pre-commit run --all-files` (`end-of-file-fixer` etc.), so an EOF defect surfaces here rather than at Final verification:

```bash
TMPDIR=$HOME/.cache uv run pytest tests/test_generation.py \
  -k "surface_map or precommit_config_valid or all_toggles_on_passes_full_gate" -v
```
Expected: all PASS. (If `test_precommit_config_valid` fails on `end-of-file-fixer`, the surface-map block left a trailing `\n\n` in a policy-off render — fix the `{% endif -%}` trim in Step 4.)

- [ ] **Step 7: Lint + typecheck**

Run:
```bash
just lint && just fmt-check && just typecheck
```
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add template/AGENTS.md.jinja tests/test_generation.py
git commit -m "feat(template): add dependency surface-map to AGENTS.md"
```

---

### Task 8: `CHANGELOG.md` — `[Unreleased] / ### Added`

**Files:**
- Modify: `CHANGELOG.md` (add a new `### Added` subsection under the empty `## [Unreleased]` heading at line 8, before `## [0.1.0]` at line 10)

**Interfaces:**
- Consumes: nothing.
- Produces: the changelog entry for the **template-side** additions only (downstreams receive these on `copier update`). The maintainer-only changes (`deps-template`, the maintainer `renovate.json`, the `_render` fixture pin) are deliberately **excluded** — they don't ship downstream.

- [ ] **Step 1: Add the `### Added` subsection**

`## [Unreleased]` (line 8) is currently empty. Insert a `### Added` subsection between it and `## [0.1.0] - 2026-06-25` (line 10), mirroring the Keep-a-Changelog style used under `[0.1.0]`:

```markdown
## [Unreleased]

### Added

- `just deps` recipe (`uv tree --frozen`) — print the resolved dependency graph from the
  committed lock, no resolve or network.
- A dependency surface-map in `AGENTS.md`'s `## Dependencies` section: every dependency
  surface (uv/Python, mise tools, pre-commit hooks, GitHub Actions, scanner pins), the one
  command to read each, and the trust model (in-repo map + `just deps` = record; Renovate =
  freshness + cross-check; zizmor = Actions SHA-pin enforcement).

## [0.1.0] - 2026-06-25
```

(The `[Unreleased]` compare link already exists at the file foot — no link plumbing needed.)

- [ ] **Step 2: Sanity-check the file still parses as Markdown**

Run:
```bash
git diff CHANGELOG.md
```
Expected: a clean additive diff — new `### Added` block under `[Unreleased]`, `[0.1.0]` untouched.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note just deps recipe and dependency surface-map"
```

---

### Task 9: Verify the template `renovate.json` covers every shipped surface

**Files:**
- Inspect only: `template/{% if enable_renovate %}renovate.json{% endif %}.jinja` (the conditional-name idiom — there is **no** literal `template/renovate.json.jinja`). Change **only** if a coverage gap is found (none expected).

**Interfaces:**
- Consumes: nothing.
- Produces: a documented confirmation (or, if a gap is found, a minimal config fix + a generation-test assertion for it).

**Already-shipped config (for reference):** `extends: ["config:recommended", "helpers:pinGitHubActionDigests"]`, `lockFileMaintenance` weekly, `"pre-commit": {"enabled": true}`, and one regex `customManager` matching `uvx (semgrep|zizmor|pip-audit)@X.Y.Z` in `justfile` + `*.yml`/`*.yaml`.

- [ ] **Step 1: Map each surface to a manager (surface-by-surface)**

Confirm each shipped surface is covered:

| Surface | Covered by | Confirm |
|---|---|---|
| uv / pyproject deps + `uv.lock` | `config:recommended` (`pep621`/uv) + weekly `lockFileMaintenance` | ✓ (inherited) |
| build-system floor (`uv_build` in `[build-system].requires`, library only) | `config:recommended` `pep621` manager (it extracts `build-system.requires`) | ✓ (inherited; this is the surface Task 7's build-backend row claims) |
| `setup-uv` `version:` inputs (ci/scan/mutation workflows) | `config:recommended` `github-actions` manager (depName `astral-sh/uv` — a **distinct** dep from the mise `uv` pin) | ✓ (inherited) — note these and the mise `uv` pin bump in **separate** PRs unless grouped |
| GitHub Actions `uses:` SHAs | `config:recommended` `github-actions` + `helpers:pinGitHubActionDigests` | ✓ (inherited) |
| pre-commit `rev:` SHAs | `"pre-commit": {"enabled": true}` (off by default in Renovate) | ✓ (explicit) |
| `uvx` scanner pins (semgrep/zizmor/pip-audit) in `justfile` + `scan.yml` | regex `customManager` | ✓ (all three in the alternation; file patterns cover both) |
| mise tools: `python`, `uv`, `just`, `copier` | `config:recommended` `mise` manager | ✓ (inherited) |
| mise tool: `gitleaks` | `config:recommended` `mise` manager **iff** its mise backend resolves to a Renovate datasource | **verify in Step 2** |

- [ ] **Step 2: Verify `gitleaks`'s mise backend is Renovate-resolvable**

`gitleaks` ships only as a `mise.toml` pin (single source of truth; `scan.yml` installs it via `mise`, no inline version). Renovate's `mise` manager can update it only if `gitleaks`'s registry backend maps to a supported datasource.

Run:
```bash
mise registry | grep -i '^gitleaks'
```
Expected: a backend mapping (e.g. `gitleaks  aqua:gitleaks/gitleaks` or `ubi:gitleaks/gitleaks`). Confirm that backend is one Renovate's `mise` manager supports (aqua → `github-releases`/`github-tags`; ubi/core → GitHub datasources). If `mise` is not on PATH, instead inspect the registry mapping at <https://mise.jdx.dev/registry.html> for `gitleaks` and cross-reference Renovate's `mise` manager docs (<https://docs.renovatebot.com/modules/manager/mise/>) for supported backends.

- [ ] **Step 3: Record the outcome**

- **If covered (expected):** no config change. State the conclusion in the task's review comment: "template `renovate.json` covers all shipped surfaces; `gitleaks` resolves via the `mise` `<backend>` backend." No commit.
- **If a gap is found (unexpected):** add the minimal fix (e.g. a `customManager` for the uncovered pin) to `template/{% if enable_renovate %}renovate.json{% endif %}.jinja`, **and** add a present-when-`enable_renovate`-on assertion to `tests/test_generation.py` (house contract). Re-validate with `renovate-config-validator` (see Task 1 Step 2). Then commit:
  ```bash
  git add "template/{% if enable_renovate %}renovate.json{% endif %}.jinja" tests/test_generation.py
  git commit -m "fix(template): cover <surface> in renovate.json"
  ```

---

## Final verification (run after all tasks)

- [ ] **Full suite green (with the disk-exhaustion workaround):**

```bash
TMPDIR=$HOME/.cache just test
```
Expected: all generation + roundtrip tests pass (the new `deps`/surface-map tests included; existing tests unaffected).

- [ ] **Harness lint + typecheck:**

```bash
just lint && just fmt-check && just typecheck
```
Expected: clean (`failOnWarnings` makes any basedpyright finding fail).

- [ ] **Maintainer recipes still work end-to-end:** `just deps` and `just deps-template` both exit 0 (Task 4).

- [ ] **Optional pre-merge robustness check (oldest interpreter).** Local single-Python runs can pass while the CI matrix fails (copier `_tasks` read plumbum's `local.env` snapshot — see auto-memory `generation-tests-matrix-only-failures`). Before relying on the work cross-platform, run the generation suite under the oldest matrix Python:
```bash
TMPDIR=$HOME/.cache UV_PYTHON=3.11 uv run pytest tests/test_generation.py -q
```
Expected: PASS.

## Self-review (completed by plan author)

- **Spec coverage:** ① maintainer `renovate.json` → Task 1; operator precondition (enable app) → Task 2; ② `deps`/`deps-template` recipes → Task 4; ③ `_render` `vcs_ref="HEAD"` → Task 3; ④ maintainer `AGENTS.md` surface-map → Task 5; ⑤ CHANGELOG → Task 8; ⑥ template `deps:` → Task 6; ⑦ template surface-map (toggle-correct) → Task 7; ⑧ verify template `renovate.json` → Task 9; ⑨ all generation assertions (unconditional, `enable_scanners`, `enable_dependency_audit`, `project_type`, `enable_sha_pin_policy`, `enable_renovate`, runtime) → Tasks 6–7. Goal criteria 1–6 all mapped. No spec section left without a task.
- **Placeholder scan:** every code/Jinja/JSON block is concrete; the one branch with a `<surface>`/`<backend>` placeholder is Task 9's *conditional* gap-fix (gap not expected) and Step 3 names how to fill it.
- **Type/name consistency:** test helpers and fixtures (`render`, `run_in`, `MINIMAL`, `FULL`, `RenderFn`, `without_interpreter_pins`, the new `_deps_section`) match the names verified in `conftest.py`/`test_generation.py`; anchors (`uv_build`, `unpinned-uses`, `semgrep`, `pip-audit`, `Renovate`, `### Inspect the dependency graph`, `| mise tools |`) match the surface-map literals authored in Task 7.

## Notes surfaced during grounding (not in scope — flag to the user)

- The maintainer `AGENTS.md` `## Release` section says "the repo carries no tags until the first release is cut," but `v0.1.0` **is** tagged. The guidance (tag before announcing) still holds for future releases, so the sentence is only mildly stale — left untouched to respect scope. Worth a one-line fix in a future docs pass.
- The maintainer config freezes `uv` and `copier` rather than letting the bot bump them. Renovate **does** track every `uv` site natively (`uv` via the `mise` manager, `astral-sh/uv` via the `github-actions` manager), so a custom `pypi`/`uv` `customManager` for the `setup-uv` inputs would be redundant — it double-matches the built-in `astral-sh/uv` handling. If automated freshness is wanted later, the clean option is to drop the `enabled:false` and add `"groupName": "uv"` (and one for `"copier"`) so each tool's sites move together in a single PR; verify with `renovate --dry-run` that they land in one branch.

## Review fixes applied (2026-06-26, multi-agent review)

An adversarial review (ground-truth verification of every factual claim, 5 dimension finders, an empirical worktree dry-run that applied Tasks 3/6/7 and ran the tests, per-finding verification) confirmed the plan's line numbers, names, copier internals, and version parity are all accurate, and that the mechanical core works (8 new tests pass, no regression). It also found defects, now fixed above:

- **Blocker — `just lint` (UP037):** Task 7 Step 1's `_deps_section(project: "Path")` quoted annotation fails ruff `select=ALL` because the file uses `from __future__ import annotations` → changed to bare `Path`.
- **Blocker — `vcs_ref="HEAD"` exit 128:** copier's dirty path runs `git add -A` over the whole tree; an untracked nested git repo (`.claude/worktrees/…`, created by this plan's own `superpowers` execution) aborts the render → added a clean-tree precondition to Global Constraints, corrected the grounding fact, and flagged that `just deps-template` and Step 5 hit the same path.
- **Blocker — EOF `\n\n` breaks `end-of-file-fixer`:** the surface-map left a trailing blank line in policy-off renders (default MINIMAL), failing `test_precommit_config_valid` and downstream `pre-commit` → fixed with `{% endif -%}`; Step 5 now checks EOF bytes + newline budget, Step 6 now runs the whole-tree-hook gate tests.
- **Blocker — Renovate uv rule mis-scoped:** `matchDepNames:["uv"]` froze only the mise pin (depName `uv`) and left the `setup-uv` inputs (depName `astral-sh/uv`) bumping → freeze both names; rationale corrected (the github-actions manager tracks `setup-uv` natively).
- **Copier drift re-created:** Task 4 makes `copier` multi-site, invalidating "copier is single-site" → added a `copier` freeze rule + corrected the scoping rationale.
- **Map accuracy/coverage:** maintainer lead sentence no longer overclaims "every surface fresh"; maintainer `uvx` grep now includes `justfile` (the `uvx copier@` pin); both maps now name the `setup-uv version:` inputs; `pep621` replaces the nonexistent "uv manager"; the scanner row's read-command now reads gitleaks from `mise.toml`; Task 9's table adds the `setup-uv` and build-system-floor rows.
- **Process:** per-task steps (Tasks 3/6/7) now run `just fmt-check`; Task 2 records the CI-cost + App-permission acceptance; Task 4 Step 2 verifies `just deps` is not hollow on the `package = false` maintainer project.

Two finder claims were refuted during verification (false positives); the `_deps_section` extractor was specifically cleared (the inline `` `## Detected Dependencies` `` does not break the `\n## ` split).
