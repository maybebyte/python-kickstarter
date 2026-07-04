# Dogfood dependency-audit (pip-audit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the template's `enable_dependency_audit` (pip-audit) gate onto the maintainer root — a `just audit` recipe plus one blocking CI step — closing gap #5, green from the first run.

**Architecture:** Four maintainer-root files, zero `template/` files. A `just audit` recipe exports the full locked graph and runs `uvx pip-audit@2.10.1`; a `pip-audit` step in the existing `scan` job of `test-template.yml` enforces it in CI; `.gitignore` backstops the temp export; `AGENTS.md` documents the gate + pin-sync obligation.

**Tech Stack:** just, uv (`uv export`), `uvx pip-audit@2.10.1`, GitHub Actions, mise (toolchain), GPG-signed Conventional Commits.

## Global Constraints

- **Design spec:** `docs/superpowers/specs/2026-07-03-dogfood-dependency-audit-design.md` — the authority; every task mirrors it.
- **Mirror, don't diverge.** Only two command-content divergences from the template are permitted, both forced: drop `--no-dev`; run via `uvx pip-audit@2.10.1` (no pyproject dep).
- **`--no-dev` MUST be dropped in BOTH the recipe and the CI step** — with `package = false` and all deps in `[dependency-groups] dev`, `--no-dev` exports 0 packages and the gate passes vacuously. (Verified: `--no-dev` → 0 pins; without → 35.)
- **pip-audit pin `2.10.1` at exactly 3 maintainer sites:** the `just audit` recipe, the CI step, the AGENTS.md prose. **No** `mise.toml` and **no** `pyproject.toml` pip-audit literal.
- **Touch zero `template/` files** → no `tests/test_generation.py` change, no `CHANGELOG.md` entry, no version tag.
- **Do not touch** the existing `scan`-job steps (semgrep, mise-action, gitleaks), the other CI jobs, the zizmor `1.26.1` pin, or the gitleaks `8.30.1` mise pin.
- **Commits:** Conventional Commits; GPG-signed (automatic via Split GPG — the "not sending a push certificate" warning is expected); author `Ashlen <dev@anthes.is>`; **no AI-attribution / Co-Authored-By trailer**. Stage files **surgically** (`git add <exact paths>`), never `git add -A` (untracked docs/scratch must not be swept in).
- **Branch:** `chore/dogfood-dependency-audit` (already created off updated `main`).
- **Non-interactive shell note:** the Bash tool shell does not activate mise. `uv`/`uvx` resolve on PATH, but run `just` recipes via `mise exec -- just <recipe>` for robustness.

---

### Task 0: Commit the design spec + this plan

**Files:**
- Add: `docs/superpowers/specs/2026-07-03-dogfood-dependency-audit-design.md` (already written)
- Add: `docs/superpowers/plans/2026-07-03-dogfood-dependency-audit.md` (this file)

- [ ] **Step 1: Stage the two docs surgically**

```bash
git add docs/superpowers/specs/2026-07-03-dogfood-dependency-audit-design.md \
        docs/superpowers/plans/2026-07-03-dogfood-dependency-audit.md
```

- [ ] **Step 2: Verify only those two files are staged**

Run: `git diff --cached --name-only`
Expected: exactly the two paths above, nothing else.

- [ ] **Step 3: Commit**

```bash
git commit -m "docs(plans): add dogfood dependency-audit design + plan"
```

---

### Task 1: `just audit` recipe + `.gitignore` backstop

**Files:**
- Modify: `justfile` (append an `audit` recipe after the `scan` recipe)
- Modify: `.gitignore` (append `requirements-audit.txt`)

**Interfaces:**
- Produces: a `just audit` recipe that exits 0 when the locked graph has no known advisories, non-zero on a CVE or a stale lock.

- [ ] **Step 1: Append the `audit` recipe to `justfile`**

Anchor on the final two lines of the existing `scan` recipe. Replace:

```just
    # `git` (not `dir`): scan committed history like CI, catching secrets committed then deleted.
    gitleaks git . --redact --exit-code 1
```

with:

```just
    # `git` (not `dir`): scan committed history like CI, catching secrets committed then deleted.
    gitleaks git . --redact --exit-code 1

# Out-of-band dependency vulnerability audit: pip-audit over the FULL locked graph.
# `--no-dev` is dropped (unlike the template): package=false puts every dep in the
# dev group, so the template's --no-dev would export 0 packages and pass vacuously.
# Enforced in CI by the `scan` job, not a `ci` recipe (there is none).
audit:
    uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
    uvx pip-audit@2.10.1 -r requirements-audit.txt
    rm -f requirements-audit.txt
```

- [ ] **Step 2: Append the `.gitignore` entry**

Anchor on the current final entry. Replace:

```gitignore
# Agent worktrees/state. Nested git repos here also break `vcs_ref="HEAD"` renders
# (copier's `git add -A` stages them as phantom submodules → exit 128).
/.claude/
```

with:

```gitignore
# Agent worktrees/state. Nested git repos here also break `vcs_ref="HEAD"` renders
# (copier's `git add -A` stages them as phantom submodules → exit 128).
/.claude/

# pip-audit's temp export (`just audit`); rm'd on success, gitignored so a failed run leaves a clean tree.
requirements-audit.txt
```

- [ ] **Step 3: Prove the `--no-dev` drop is load-bearing (non-vacuity)**

Run:
```bash
echo "with --no-dev:"; uv export --frozen --no-emit-project --no-hashes --no-dev 2>/dev/null | grep -c '==' || true
echo "without --no-dev:"; uv export --frozen --no-emit-project --no-hashes 2>/dev/null | grep -c '=='
```
Expected: `with --no-dev:` → `0`; `without --no-dev:` → `35`.

- [ ] **Step 4: Run the gate and confirm it is green today**

Run: `mise exec -- just audit`
Expected: pip-audit prints `No known vulnerabilities found in <~35> packages` (benign `cachecontrol` cache warnings may appear) and exits 0.

- [ ] **Step 5: Confirm the tree is clean (temp file removed + gitignored)**

Run: `git status --short`
Expected: shows only `justfile` and `.gitignore` as modified (`M`). **`requirements-audit.txt` must NOT appear** (removed by the recipe's `rm`; gitignored as a backstop).

- [ ] **Step 6: Commit**

```bash
git add justfile .gitignore
git commit -m "feat(audit): dogfood pip-audit — just audit recipe + gitignore backstop"
```

---

### Task 2: `pip-audit` step in the CI `scan` job

**Files:**
- Modify: `.github/workflows/test-template.yml` (insert one step into the existing `scan` job)

**Interfaces:**
- Consumes: the `scan` job's existing `actions/checkout` (`fetch-depth: 0`) and `astral-sh/setup-uv` (provides `uv`).
- Produces: a blocking `pip-audit` PR-gate step.

- [ ] **Step 1: Insert the `pip-audit` step (after `setup-uv`, before `semgrep`)**

Anchor uniquely on the scan job's setup-uv → semgrep boundary. Replace:

```yaml
          version: "0.11.23"
          enable-cache: true
      - name: semgrep
        run: uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
```

with:

```yaml
          version: "0.11.23"
          enable-cache: true
      - name: pip-audit
        run: |
          uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
          uvx pip-audit@2.10.1 -r requirements-audit.txt
      - name: semgrep
        run: uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
```

(Note: the export line has **no `--no-dev`** — same as the recipe. No `rm` — the runner is ephemeral, mirroring the template `scan.yml`.)

- [ ] **Step 2: Verify the workflow is still valid YAML (network-free)**

Run (via the project venv — PyYAML is not on the bare/mise `python3`, only in the uv venv):
```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/test-template.yml')); print('YAML OK')"
```
Expected: `YAML OK` (no exception).

- [ ] **Step 3: Verify the edit is surgical — one step added, nothing else changed**

Run: `git diff --unified=1 .github/workflows/test-template.yml`
Expected: a pure addition of the 4-line `pip-audit` step between `enable-cache: true` and `- name: semgrep`; the semgrep / mise-action / gitleaks steps and every other job untouched.

- [ ] **Step 4: Confirm zizmor stays green over the edited workflow**

Run: `GH_TOKEN=$(gh auth token 2>/dev/null) uvx zizmor@1.26.1 --persona=regular .`
Expected: no findings (exit 0). The new step adds no `uses:` action and no `${{ }}` expression, so there is no new injection or unpinned-action surface. (If `gh` is unauthenticated, zizmor still runs its offline audits; a token only enables online checks.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/test-template.yml
git commit -m "ci(audit): add pip-audit step to the scan job"
```

---

### Task 3: Document the gate in `AGENTS.md`

**Files:**
- Modify: `AGENTS.md` (new `## Dependency audit` H2 between `## Scanning` and `## Add a guardrail layer`)

- [ ] **Step 1: Insert the new section**

Anchor on the `## Scanning` section end → `## Add a guardrail layer` boundary. Replace:

```markdown
pre-commit "bump both `rev:` pins together" obligation.)

## Add a guardrail layer
```

with (the outer fence below is 4 backticks **only so this plan can show a nested ` ```bash ` block** — in `AGENTS.md` itself type all fences as plain three-backtick fences):

````markdown
pre-commit "bump both `rev:` pins together" obligation.)

## Dependency audit

```bash
just audit   # out-of-band dependency vulnerability audit: pip-audit over the full locked graph
```

`just audit` exports the fully-resolved lockfile (`uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt`) and runs `uvx pip-audit@2.10.1 -r requirements-audit.txt`. It is out-of-band (chained into no recipe), but CI enforces it: the `pip-audit` step in the `scan` job of `.github/workflows/test-template.yml` is a blocking PR gate. Unlike semgrep — which scans 0 files here — pip-audit is the **substantive** dependency gate: it audits the real ~35-package dev+transitive graph (copier / pytest / ruff / basedpyright / pre-commit / plumbum / pyyaml + transitives), because **`--no-dev` is dropped**. Never restore `--no-dev`: `package = false` puts every dep in the dev group, so `--no-dev` would export 0 packages and pass vacuously. `requirements-audit.txt` is `rm`'d on success, gitignored, and lingers (harmlessly) only after a failed run. pip-audit is the one **non-hermetic** step in the `scan` job — it queries the OSV/PyPI advisory DB, so this gate can turn red on a newly-published CVE (or an advisory-DB outage) independent of any code change; a `--frozen` **export** failure instead means `uv.lock` is stale (re-lock), distinct from a pip-audit non-zero (a CVE). pip-audit runs via `uvx` (no pyproject dep, like semgrep/zizmor).

Deliberate divergences from the template's dependency-audit layer: `--no-dev` is dropped (above); pip-audit runs via `uvx pip-audit@2.10.1` in both the recipe and CI with **no** pyproject dep (the template adds `pip-audit>=2.10` to its dev group and runs `uv run pip-audit` locally); it is folded into `test-template.yml`'s `scan` job as a step (the template ships it in a standalone `scan.yml`); and it is out-of-band, not a `just ci` dependency (the template makes `audit` gating — the maintainer has no `ci` recipe).

Because nothing here re-derives the pin (no Renovate; the generation drift test reads only the *rendered* downstream), **bump every literal by hand, against the template.** pip-audit (`2.10.1`) has three maintainer sites — the `just audit` recipe, the `pip-audit` step in `test-template.yml`, and the prose above — synced to `template/.github/workflows/…scan.yml….jinja` (the only exact-version template site; the template justfile uses unpinned `uv run pip-audit` and template pyproject floors `pip-audit>=2.10`). No `mise.toml` or `pyproject.toml` pip-audit literal exists (uvx-run, unlike gitleaks). **Sync only the pin *value* — never the export flags:** the template's `uv export` keeps `--no-dev`, but the maintainer must not (it exports 0 packages here — see above), so a mechanical sync against the template would silently neuter the gate. (Mirrors the semgrep/gitleaks pin-sync note and the pre-commit "bump both `rev:` pins together" rule.)

## Add a guardrail layer
````

- [ ] **Step 2: Verify pin-sync — `2.10.1` at exactly 3 sites, none in mise/pyproject**

Run:
```bash
echo "== pin FILES (expect 3: justfile, test-template.yml, AGENTS.md) =="; grep -rl 'pip-audit@' justfile .github/workflows/test-template.yml AGENTS.md
echo "== pin literals (expect 4: 1 justfile + 1 CI + 2 AGENTS prose) =="; grep -rn 'pip-audit@' justfile .github/workflows/test-template.yml AGENTS.md
echo "== mise/pyproject (expect NO output) =="; grep -n 'pip-audit' mise.toml pyproject.toml || echo "(none — correct)"
```
Expected: **3 files** listed; **4** `pip-audit@2.10.1` literals (one in the justfile, one in the CI step, and **two** in AGENTS.md — the usage and divergences paragraphs, both spec-mandated: do NOT delete the second to force a count of 3, the "3 sites" governance is file-level); no output from the mise/pyproject grep. All literals read `2.10.1`.

- [ ] **Step 3: Verify the section placement + single new H2**

Run: `grep -n '^## ' AGENTS.md`
Expected: `## Dependency audit` appears immediately between `## Scanning` and `## Add a guardrail layer`; no other heading changed.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): document the dependency-audit gate + pin-sync obligation"
```

---

### Finishing: full verification + PR

- [ ] **Step 1: Guard the matrix render — no untracked nested git repo under `.claude/`**

Run: `find .claude -maxdepth 3 -name .git 2>/dev/null || true`
Expected: empty. If any path prints, remove that nested repo before the matrix (copier's `vcs_ref="HEAD"` render hard-fails exit 128 on a phantom submodule).

- [ ] **Step 2: Run the full generation matrix**

Ensure the roomy TMPDIR exists (the full suite overflows the 4G `/tmp`):
```bash
mkdir -p /home/user/.cache/kickstarter-test-tmp
TMPDIR=/home/user/.cache/kickstarter-test-tmp mise exec -- just test
```
Expected: all tests pass (the prior green count was 70). No `template/` file changed, so no dependency-audit generation assertion is affected and `test_tool_version_pins_have_no_drift` (which excludes pip-audit) still passes.

- [ ] **Step 3: Confirm lint / format / typecheck unaffected (no Python touched)**

Run: `mise exec -- just lint && mise exec -- just fmt-check && mise exec -- just typecheck`
Expected: all green.

- [ ] **Step 4: Confirm the branch is exactly four commits, clean tree**

Run: `git log --oneline main..HEAD && echo "---" && git status --short`
Expected: four commits (docs plan, feat audit, ci audit, docs agents); working tree clean.

- [ ] **Step 5: Finish the branch (push + PR)**

Invoke the `superpowers:finishing-a-development-branch` skill. Push `chore/dogfood-dependency-audit`; open a PR titled `feat(audit): dogfood the pip-audit dependency-audit gate on the maintainer repo` with a body following the `pr-descriptions` skill (Summary / Changes / Testing / Notes for reviewers [flag: pip-audit is the substantive gate — `--no-dev` dropped; the one non-hermetic scan step] / Related [closes gap #5]). Do **not** merge — hand off to the user, as with gaps #1 and #2.

- [ ] **Step 6: Report final CI status**

Run: `gh pr checks <N>` once CI starts.
Expected: the new `pip-audit` step passes inside the green `scan` job; all other jobs (test matrix, zizmor, typecheck, lint) stay green.

## Self-review notes (author check against the spec)

- **Spec coverage:** recipe (Task 1) · `.gitignore` (Task 1) · CI step (Task 2) · AGENTS section incl. pin-sync + `--no-dev` caveat + non-hermetic note (Task 3) · no-`template/`-touch / no-tag / no-generation-test (Global Constraints + Finishing Step 2). All spec sections map to a task.
- **Divergences:** exactly the two forced ones (drop `--no-dev`, `uvx` pin/no dep) plus the CI-fold and out-of-band placement, all documented in Task 3's prose.
- **Pin discipline:** `2.10.1` at 3 sites, verified by Task 3 Step 2; the `--no-dev`-preservation caveat guards the sync-trap.
