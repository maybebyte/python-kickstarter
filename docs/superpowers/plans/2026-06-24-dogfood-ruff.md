# Dogfood the full ruff config (`select=["ALL"]`) on the maintainer harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the template's full-fledged ruff config (`select=["ALL"]` + curated, audited ignores) onto the maintainer repo's own `tests/` harness, declare a version-capped `ruff` dev-dep, wire `just lint`/`fmt`/`fmt-check`, drive the harness to **0 ruff findings honestly**, and enforce it in CI.

**Architecture:** Maintainer-only — there is **no template-side change** (the template already ships `select=["ALL"]` by default). One workstream over the four-file `tests/` harness (`conftest.py`, `test_generation.py`, `test_update_roundtrip.py`, `__init__.py`); there is no `src/`, and `template/` is Jinja (`*.jinja`), never linted as Python. Land the config + dev-dep + recipes (gate goes live, **RED at 20**), then drive to 0 in two remediation steps — a mechanical autofix/format sweep (→ **4**) then three hand-fixes (→ **0**) — then enforce in CI and document. The split is deliberate: a reviewer can approve the large low-judgment autofix diff separately from the small high-judgment hand-edits. This mirrors the basedpyright dogfood (`docs/superpowers/plans/2026-06-23-dogfood-typecheck.md`) exactly.

**Tech Stack:** Python 3.11 (maintainer floor), ruff 0.15.x (`uv run`/dev-dep, capped `>=0.15,<0.16`), `uv`, `just`, pytest, GitHub Actions.

## Global Constraints

Every task implicitly includes these (copied verbatim from the spec, `docs/superpowers/specs/2026-06-23-dogfood-ruff-design.md`):

- **ruff pin:** `"ruff>=0.15,<0.16"` — cap-and-bump-deliberately; `select=["ALL"]` tracks every rule ruff adds, so a minor bump can redden a green tree.
- **Config is exactly config N (minimal-honest):** inline `[tool.ruff]` in `pyproject.toml`; `select=["ALL"]`; global `ignore = ["COM812", "ISC001"]` (the formatter-owned pair); `per-file-ignores` `"tests/**" = ["S101","PLR2004","S603","S607","D103","D104"]`; the shared tuning (line-length 100, mccabe ≤10, pylint limits, pydocstyle google, isort `known-first-party=["tests"]`, format double-quote + docstring-code); `target-version="py311"`, `extend-exclude=["template"]`.
- **No suppression, ever:** **no inline `# noqa`** in the final state (the three existing ones are removed, not relied on); no `select` lowering; no surface-narrowing; `extend-exclude` drops only Jinja (zero `.py`). Every committed `ignore`/`per-file-ignore` entry is load-bearing and truthfully justified. Reach zero by *fixing* defects + the audited ignore set, never by silencing a fixable one. (See the spec's "Integrity audit".)
- **Cross-gate:** after the ruff fixes, the basedpyright `recommended` gate (`just typecheck`) must stay at **0 findings** — the ruff dogfood may not redden the typecheck gate.
- **CI hardening (for the new job):** SHA-pinned actions with exact-tag comments, `persist-credentials: false`, pinned `uv` `0.11.23` — match the existing jobs in `.github/workflows/test-template.yml` exactly. Never bump an Action SHA without updating its exact-tag comment.
- **Release gating:** changes only the maintainer repo, not what generated projects are held to — no downstream blast radius and **no `_migrations` entry**. Still land it **before the first release tag** (alongside the typecheck dogfood) so `v0.1.0` ships a harness that dogfoods both gates.
- **No template-side change:** the template already ships `select=["ALL"]` (`ruff_ruleset: all`); nothing to raise. Do not touch `template/`.

## Verified finding-count walk (ruff is the oracle)

Every count below was reproduced end-to-end on an isolated `git archive HEAD` copy with the real gate, ruff 0.15.19 (`uvx --from 'ruff>=0.15,<0.16' ruff`, the version `uv run ruff` resolves to under the cap). The bare-maximal baseline (`select=["ALL"]`, **empty** ignores) is **166** with `--ignore-noqa` (163 literal) — this is the conceptual zero-ignore reference and is **never a committed state**; the first committed state is config N at 20.

| after task | maintainer `ruff check .` | rule histogram |
|---|--:|---|
| Task 1 (config N live, pre-remediation) | **20** | `E501`×5, `RUF100`×3, `PT018`×3, `TC003`×2, `D205`×2, `D202`×1, `UP013`×1, `PLC0415`×1, `D403`×1, `PLW1510`×1 |
| Task 2 (`ruff check --fix --unsafe-fixes .` + `ruff format .`) | **4** | `D205`×2, `PLC0415`×1, `PLW1510`×1 |
| Task 3 (3 manual fixes) | **0** | — (GREEN), `ruff format --check .` clean |

> **Why config N is 20, not 19 (= 166 − 147 ignored):** ignoring `S603`/`S607` turns one more stale `noqa` (`test_update_roundtrip.py:98`) into a `RUF100` finding, so the measured residual is 20. The autofix in Task 2 then strips all three `RUF100` noqa cleanly; `PLW1510` survives at the now-noqa-free line 98 and is hand-fixed in Task 3.

## File Structure

The `tests/` harness is the only Python surface; there is no `src/`.

- `pyproject.toml` — add the `ruff` dev-dep and the inline `[tool.ruff]` config N (Task 1).
- `uv.lock` — regenerated by `uv sync` when the dep lands (Task 1). Tracked; keep in sync.
- `justfile` — add `fmt` + `fmt-check` recipes (Task 1); the existing `lint` recipe (`uv run ruff check .`) already matches config N and becomes config-driven once `[tool.ruff]` exists — leave it.
- `tests/conftest.py` — autofix only: `D202` (blank line after docstring), `RUF100` (strip the `:56` noqa) (Task 2).
- `tests/test_generation.py` — autofix (`E501`×5, `TC003`×1, `UP013`×1, `D403`×1, `PT018`×2) (Task 2) + manual (`PLC0415` import hoist, `D205`×2 summaries) (Task 3).
- `tests/test_update_roundtrip.py` — autofix (`TC003`×1, `PT018`×1, `RUF100` strip the `:21` and `:98` noqa) (Task 2) + manual (`PLW1510` `check=False`) (Task 3).
- `.github/workflows/test-template.yml` — add the `lint` CI job (Task 4).
- `AGENTS.md` — document `just lint`/`fmt` (Task 5).

---

### Task 1: Establish the ruff `select=["ALL"]` gate (config N)

Installs the gate so every later step has a runnable oracle. The gate is **RED (20) on purpose** at the end of this task — the "watch the test fail" step. CI does not enforce it until Task 4, and `just test` (pytest) stays green throughout, so no CI-gated state is ever red.

**Files:**
- Modify: `pyproject.toml` (add dev-dep + `[tool.ruff]` config N)
- Modify: `justfile` (add `fmt` + `fmt-check` recipes)
- Modify: `uv.lock` (via `uv sync`)

**Interfaces:**
- Produces: `just lint` (`uv run ruff check .`), `just fmt`, `just fmt-check`, and an inline `[tool.ruff]` config N that every later task verifies against.

- [ ] **Step 1: Add the dev-dependency.** Edit `pyproject.toml`, in `[dependency-groups].dev`, append the ruff line:

```toml
[dependency-groups]
dev = [
    "copier>=9.6,<10",
    "pytest>=8",
    "pyyaml>=6",
    "basedpyright>=1.39,<1.40",
    "ruff>=0.15,<0.16",
]
```

- [ ] **Step 2: Add the inline config N.** Edit `pyproject.toml`, append after the `[tool.basedpyright]` block (the current last block):

```toml

[tool.ruff]
line-length = 100
target-version = "py311"            # the requires-python floor (template uses the chosen python_version)
extend-exclude = ["template"]       # parity with basedpyright; template/ is Jinja, count-neutral

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "COM812",   # formatter-owned: conflicts with `ruff format` (ruff's own formatter-compat guidance)
    "ISC001",   # formatter-owned: the documented companion to COM812 under `ruff format`
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-args = 8
max-branches = 12
max-returns = 6
max-statements = 50

[tool.ruff.lint.pydocstyle]
convention = "google"               # selects D211/D212; resolves the D203/D213 conflicts by convention

[tool.ruff.lint.isort]
known-first-party = ["tests"]       # no package — tests/ is the only first-party root

[tool.ruff.lint.per-file-ignores]
# The only Python surface is the pytest harness under tests/.
"tests/**" = [
    "S101",     # pytest IS assert-based (it rewrites bare asserts for introspection)
    "PLR2004",  # a literal threshold is the substance of a test assertion
    "S603",     # the harness deliberately drives git/just/uv; inputs are literal command lists
    "S607",     # ...invoked by name on PATH (shutil.which over REQUIRED_TOOLS); absolute paths regress portability
    "D103",     # test functions are self-documenting via descriptive names
    "D104",     # tests/ is an (empty) package marker
]

[tool.ruff.format]
quote-style = "double"
docstring-code-format = true
```

- [ ] **Step 3: Add the recipes.** Edit `justfile`, append (the existing `lint` recipe already runs `uv run ruff check .` — leave it; it is now config-driven):

```make
# Auto-format + apply safe lint fixes to this repo's own tooling (the tests/ harness).
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# CI's format gate: fail if anything is unformatted.
fmt-check:
    uv run ruff format --check .
```

- [ ] **Step 4: Sync the environment + lockfile.**

Run: `uv sync`
Expected: resolves and installs `ruff==0.15.19` (or the latest `0.15.x`); `uv.lock` is updated.

- [ ] **Step 5: Run the gate and watch it fail (RED).**

Run: `just lint`
Expected: **FAIL**, exit non-zero, ~20 findings reported. Confirm the exact total + histogram with:

Run: `uv run ruff check --output-format json . | uv run python -c "import json,sys,collections; g=json.load(sys.stdin); print(len(g)); print(collections.Counter(x['code'] for x in g))"`
Expected: `20` and `Counter({'E501': 5, 'RUF100': 3, 'PT018': 3, 'TC003': 2, 'D205': 2, 'D202': 1, 'UP013': 1, 'PLC0415': 1, 'D403': 1, 'PLW1510': 1})`

- [ ] **Step 6: Confirm pytest is unaffected.**

Run: `uv run pytest tests/ --co -q | tail -3`
Expected: collection succeeds (no import/syntax errors); test count unchanged.

- [ ] **Step 7: Commit.**

```bash
git add pyproject.toml uv.lock justfile
git commit -m "build(lint): wire ruff select=ALL gate over tests/"
```

---

### Task 2: Mechanical autofix + format sweep (20 → 4)

One mechanical change clears 16 of the 20 findings: `ruff check --fix --unsafe-fixes .` then `ruff format .`. The `--unsafe-fixes` flag is required (`PT018`, `UP013`, `TC003` are unsafe fixes); it is used here as a one-time command, not baked into the `fmt` recipe (which stays safe-only). What this clears, all behavior-preserving:

| rule | sites (config-N line numbers) | fix |
|---|---|---|
| `E501`×5 | `test_generation.py:81,343,389,461,519` | formatter reflows |
| `TC003`×2 | `test_generation.py:8`; `test_update_roundtrip.py:7` | `Path` → `TYPE_CHECKING` block (both files have `from __future__ import annotations`) |
| `UP013`×1 | `test_generation.py:32` | `_PreCommit` functional → class form; **`_Renovate` correctly stays functional** (its `pre-commit` key is hyphenated, so the class form is impossible) |
| `D202`×1 | `conftest.py:30` | drop the blank line after the docstring |
| `D403`×1 | `test_generation.py:263` | capitalize the first word (`semgrep` → `Semgrep`) |
| `PT018`×3 | `test_generation.py:339,437`; `test_update_roundtrip.py:93` | split composite `assert a and b` into two asserts (failures become more precise) |
| `RUF100`×3 | `conftest.py:56`; `test_update_roundtrip.py:21,98` | strip the now-stale `noqa` (`S603`/`S607` are ignored by config N) |

After this, **4 findings remain** — `D205`×2, `PLC0415`×1, `PLW1510`×1 — all genuinely manual (no ruff autofix). The tree is still RED at 4; that is expected and not CI-gated (CI lands in Task 4).

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_generation.py`
- Modify: `tests/test_update_roundtrip.py`

- [ ] **Step 1: Verify RED for this step.** `just lint` → 20 findings (from Task 1).

- [ ] **Step 2: Apply autofixes (to a fixpoint), then format.**

Run: `uv run ruff check --fix --unsafe-fixes .`
Then: `uv run ruff format .`
Expected: ruff applies fixes to a fixpoint and the formatter reformats the changed files (the exact reformatted-file count is not load-bearing — the count check in Step 3 is the gate).

- [ ] **Step 3: Verify the count drops to 4 (only the manual set).**

Run: `uv run ruff check --output-format json . | uv run python -c "import json,sys,collections; g=json.load(sys.stdin); print(len(g)); print(collections.Counter(x['code'] for x in g))"`
Expected: `4` and `Counter({'D205': 2, 'PLC0415': 1, 'PLW1510': 1})`

**Checkpoint (autofix behaved as designed):** the four residual codes are exactly `D205`/`PLC0415`/`PLW1510` — no new rule appeared, and all three `RUF100` (the stale `noqa`) are gone. Confirm zero `# noqa` survived the strip:

Run: `grep -rn "# noqa" tests/`
Expected: **no output** (the three originals were stripped by `RUF100 --fix`).

- [ ] **Step 4: Confirm the `_PreCommit`/`_Renovate` rewrite is correct (UP013 boundary).**

Run: `grep -n "class _PreCommit\|_Renovate = TypedDict" tests/test_generation.py`
Expected: both lines present — `class _PreCommit(TypedDict):` (converted) **and** `_Renovate = TypedDict(...)` (still functional, because `pre-commit` is not a valid identifier).

- [ ] **Step 5: Confirm pytest still collects.**

Run: `uv run pytest tests/ --co -q | tail -3`
Expected: collection succeeds, unchanged count.

- [ ] **Step 6: Commit.**

```bash
git add tests/conftest.py tests/test_generation.py tests/test_update_roundtrip.py
git commit -m "style(lint): apply ruff autofix and formatter to tests/"
```

---

### Task 3: Hand-fix the residual 4 findings (4 → 0)

The last four need judgment, not autofix. All are behavior-preserving. Each edit below is **content-anchored** (not line-numbered) because Task 2's autofix shifted line numbers (e.g. `PLC0415` moved 173 → 190) — apply them by matching the exact `old` text shown. Verified end-to-end: these exact edits reach **0** with `ruff format --check` clean and no new findings (the capitalized `D205` summaries do not re-trip `D403`).

**Files:**
- Modify: `tests/test_generation.py`
- Modify: `tests/test_update_roundtrip.py`

- [ ] **Step 1: Verify RED for this step.** `just lint` → 4 (`D205`×2, `PLC0415`×1, `PLW1510`×1).

- [ ] **Step 2: Fix `PLC0415` — hoist the function-local `import copier` to the top third-party group.**

In `tests/test_generation.py`, add `copier` to the top-of-file import group. Change:

```python
import pytest
import yaml
```

to:

```python
import copier
import pytest
import yaml
```

Then remove the function-local import inside `test_precommit_install_task_runs`. Change:

```python
    """The copy-only hook-install task fires when the hidden flag is left at default."""
    import copier

    dst = tmp_path / "installed"
```

to:

```python
    """The copy-only hook-install task fires when the hidden flag is left at default."""
    dst = tmp_path / "installed"
```

- [ ] **Step 3: Fix `PLW1510` — add an explicit `check=False`.**

In `tests/test_update_roundtrip.py`, the `just ci` call's `# noqa` was stripped by Task 2's `RUF100` autofix, so the line is now noqa-free. The `assert ci.returncode == 0` two lines below is the real check, so `check=False` is behavior-preserving. Change:

```python
    ci = subprocess.run(["just", "ci"], cwd=dst, capture_output=True, text=True)
```

to:

```python
    ci = subprocess.run(["just", "ci"], cwd=dst, capture_output=True, text=True, check=False)
```

- [ ] **Step 4: Fix `D205`×2 — give each multi-line docstring a one-line summary + blank line.**

In `tests/test_generation.py`, change:

```python
    """enable_sha_pin_policy ships the zizmor CI audit unconditionally, but the SHA-pin
```

to:

```python
    """The SHA-pin audit and its policy test are independent toggles.

    enable_sha_pin_policy ships the zizmor CI audit unconditionally, but the SHA-pin
```

and change:

```python
    """The zizmor CI step is gated solely on enable_sha_pin_policy and is absent from the
```

to:

```python
    """Only this generation assertion guards the gated zizmor CI step.

    The zizmor CI step is gated solely on enable_sha_pin_policy and is absent from the
```

- [ ] **Step 5: Verify GREEN (0 findings) + format clean.**

Run: `just lint`
Expected: **PASS**, exit 0, `All checks passed!`
Run: `just fmt-check`
Expected: exit 0, `N files already formatted`.
Confirm the total with: `uv run ruff check --output-format json . | uv run python -c "import json,sys; print(len(json.load(sys.stdin)))"` → `0`

- [ ] **Step 6: Verify the cross-gate (basedpyright stays 0).** The `import` hoist, `check=False`, and docstring text are all type-neutral; confirm the typecheck gate is unreddened.

Run: `just typecheck`
Expected: exit 0, 0 findings.

- [ ] **Step 7: Verify the runtime touchpoints are behavior-preserving.** Run the tests whose bodies were hand-edited (these render the template; allow time):

Run: `uv run pytest tests/test_generation.py::test_precommit_install_task_runs tests/test_generation.py::test_sha_pin_audit_ships_without_policy_tests tests/test_generation.py::test_zizmor_audit_absent_when_sha_pin_policy_off tests/test_update_roundtrip.py -q`
Expected: all pass.

- [ ] **Step 8: Commit.**

```bash
git add tests/test_generation.py tests/test_update_roundtrip.py
git commit -m "test(lint): hand-fix the residual ruff findings to zero"
```

---

### Task 4: Enforce the gate in CI

A dedicated single-runner `lint` job (lint/format are interpreter-version-independent), mirroring the existing `typecheck`/`zizmor` jobs' hardening exactly.

**Files:**
- Modify: `.github/workflows/test-template.yml`

- [ ] **Step 1: Add the job.** Edit `.github/workflows/test-template.yml`, append after the `typecheck` job (keep the two-space `jobs:` indentation):

```yaml

  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
        with:
          version: "0.11.23"
          enable-cache: true
      - name: Install dependencies
        run: uv sync
      - name: Lint (ruff check, select=ALL)
        run: uv run ruff check .
      - name: Format check (ruff format --check)
        run: uv run ruff format --check .
```

- [ ] **Step 2: Validate the workflow YAML parses.**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/test-template.yml')); print('valid yaml')"`
Expected: `valid yaml`

- [ ] **Step 3: Confirm the job's commands pass locally (re-assert Task 3's GREEN).**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: both exit 0.

- [ ] **Step 4: Commit.**

```bash
git add .github/workflows/test-template.yml
git commit -m "ci: enforce ruff check and format --check on push and PR"
```

---

### Task 5: Document `just lint`/`fmt` in AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the subsection.** Edit `AGENTS.md`, insert immediately after the `## Type-check this repo` block (after its `failOnWarnings` paragraph, before `## Add a guardrail layer`). The literal text to paste:

````markdown
## Lint & format this repo

```bash
just lint        # ruff check . — select=["ALL"] over tests/ (config-derived, audited ignores)
just fmt         # ruff format . + ruff check --fix . (apply safe fixes)
just fmt-check   # ruff format --check . (CI's format gate)
```

The maintainer harness runs the same full `select=["ALL"]` ruleset the template ships, scoped to `tests/` (the only Python surface; `template/` is Jinja). Every config-level ignore is load-bearing and audited — there are **no inline `# noqa`**. CI enforces `ruff check` + `ruff format --check` (the `lint` job in `.github/workflows/test-template.yml`).

````

- [ ] **Step 2: Verify the doc claims are true (the named recipes exist).**

Run: `just --list | grep -E "lint|fmt"`
Expected: `lint`, `fmt`, and `fmt-check` are all listed.

- [ ] **Step 3: Commit.**

```bash
git add AGENTS.md
git commit -m "docs: document the just lint and fmt gate"
```

---

## Final verification (whole change)

- [ ] **Maintainer lint gate:** `just lint` → exit 0, `All checks passed!`; `just fmt-check` → exit 0.
- [ ] **Cross-gate (typecheck unreddened):** `just typecheck` → exit 0, 0 findings.
- [ ] **No suppression introduced:** `grep -rn "# noqa" tests/` returns nothing — empty output is the pass. (All three original `noqa` were removed; none added.)
- [ ] **No `select` lowering / surface-narrowing:** `grep -n 'select = ' pyproject.toml` shows `select = ["ALL"]`; `extend-exclude` lists only `["template"]` (zero `.py`).
- [ ] **Full runtime suite:** `just test` → green (renders the answer matrix, installs each project, runs its `just ci`; the autofix + hand-edits are behavior-preserving). Slow (minutes) — this is the comprehensive gate.
- [ ] **Working tree:** only intended files changed; any scratch render dirs remain untracked/uncommitted.

## Notes for the implementer (read once)

- **Order matters and is load-bearing.** Do Tasks 1→5 in sequence. The ruff count is the test: 20 → 4 → 0. If a count is off, stop and diff against the expected histogram before proceeding — a wrong count localizes the mistake.
- **Manual edits are content-anchored, not line-numbered.** Task 2's autofix shifts line numbers (the spec's tables list config-N line numbers; `PLC0415` ends up at line ~190, the two `D205` docstrings at ~422/446). Apply Task 3's edits by matching the exact `old` text, not a line number.
- **`--unsafe-fixes` is a one-time command, not a recipe.** The committed `fmt` recipe uses safe `--fix` only (mirrors the template). The `PT018`/`UP013`/`TC003` fixes are unsafe and applied once in Task 2; once at 0, `just fmt` maintains it.
- **This must land before the first release tag**, alongside the typecheck dogfood. It changes only the maintainer repo (no `_migrations`, no downstream blast radius), but do not cut `v0.1.0` until this branch merges.
- **The triage workflow is reusable.** On the next ruff minor bump (raising the `<0.16` cap), re-run the persisted triage workflow (`…/workflows/scripts/ruff-dogfood-triage-*.js`) — or just the deterministic count oracle — to re-derive the partition.
- **Deferred (explicit non-goals):** the `just ci`/`just check` aggregate recipe, `mise` tool pins for the linters, and a pytest wrapper around ruff — all out of scope.
