# Dogfood policy-tests (+ sha-pin offline gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dogfood the template's policy-tests layer onto the maintainer repo — a stdlib-only `tests/policy/test_gates.py` asserting the maintainer's own gates cannot be silently weakened — closing gap #4 and (via `test_actions_are_sha_pinned`) the offline half of gap #8.

**Architecture:** Add `tests/policy/{__init__.py,test_gates.py}` (five stdlib assertions, ROOT = maintainer root); add a `policy` recipe and chain it into `just ci` (`… test policy audit`); document it in AGENTS.md and sweep every `ci` gate-list site. No CI/dep/mise/CHANGELOG/generation-test change — the existing CI `test` job's bare `uv run pytest` already collects `tests/policy`, and `tests/test_generation.py` already asserts the template layer.

**Tech Stack:** Python 3.11 stdlib (`re`, `tomllib`, `pathlib`, `typing.cast`); pytest; ruff (`select=["ALL"]`); basedpyright (`recommended` + `failOnWarnings`); `just`; `uv`.

Design: `docs/superpowers/specs/2026-07-07-dogfood-policy-tests-design.md`.
Closes Phase-1 item #5 (gap #4 policy-tests + gap #8 sha-pin) from `docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md` §7.

## Global Constraints

- Branch `chore/dogfood-policy-tests`, cut from `main` at `b7dd8b8` (after PR #9 merged).
- Commits: Conventional Commits, GPG-signed, author `Ashlen <dev@anthes.is>`, **no** AI-attribution trailer.
- Mirror the template; document forced divergences. **Locked decisions:** fenced-only docs-can't-lie regex; **include** the `failOnWarnings is True` assertion.
- The authoritative `test_gates.py` body is the one inlined in **Task 1 Step 2** below (ruff/basedpyright/pytest all green in the design-review worktree). Use it **verbatim** — in particular the fenced docs-can't-lie test must use `cast("list[str]", …)` + an annotated `referenced: set[str]` accumulator loop, **not** a set-comprehension (which trips basedpyright `reportAny` ×3).
- **AGENTS.md prose invariants — the docs-can't-lie test parses AGENTS.md as raw text.** The extractor pairs triple-backtick runs *sequentially*, so an **odd** number of runs mispairs every fence after the offender and sweeps unrelated prose into a "block". Therefore, in AGENTS.md: **(a)** never write a literal triple-backtick run in prose — write "fenced code block", never the delimiter itself; **(b)** never write a bare `just <name>` for a non-recipe (a template-only recipe such as `fuzz`/`mutate`) anywhere, prose included — name it without the `just ` prefix. (b) is defence-in-depth: it stops a future (a)-slip from turning into a red gate. This is not hypothetical — the first draft of the Task 3 section violated (a) *while describing this very divergence*, taking AGENTS.md from 16 triple-backtick runs to 19 and failing the suite on `{fuzz, mutate}`.
- No file under `template/`; no `test-template.yml`, `pyproject.toml`, `mise.toml`, `uv.lock`, `tests/test_generation.py`, or CHANGELOG change; no inline `# noqa`; no Action SHA bump.
- Environment: run `just` via `mise exec -- just` (mise is not auto-activated in non-interactive shells); `uv`/`uvx` are on PATH. The `policy` subset (`uv run pytest tests/policy`) is fast and needs no roomy TMPDIR; only the full `just test`/`just ci` matrix does.

---

### Task 0: Commit the design spec + this plan

**Files:**
- Create: `docs/superpowers/specs/2026-07-07-dogfood-policy-tests-design.md` (already written)
- Create: `docs/superpowers/plans/2026-07-07-dogfood-policy-tests.md` (this file)

- [ ] **Step 1: Cut the feature branch**

```bash
git checkout main && git pull
git checkout -b chore/dogfood-policy-tests
```

- [ ] **Step 2: Stage and commit the docs pair**

```bash
git add docs/superpowers/specs/2026-07-07-dogfood-policy-tests-design.md docs/superpowers/plans/2026-07-07-dogfood-policy-tests.md
git commit -S -m "docs(plans): add dogfood policy-tests design + plan"
```

Expected: one commit, GPG-signed, author `Ashlen <dev@anthes.is>`, no AI trailer.

---

### Task 1: `tests/policy/` — the policy suite (gap #4 + #8)

**Files:**
- Create: `tests/policy/__init__.py` (empty)
- Create: `tests/policy/test_gates.py`

**Interfaces:**
- Consumes: the maintainer's own `pyproject.toml`, `justfile`, `AGENTS.md`, `.github/workflows/*.yml` (read at `ROOT = Path(__file__).resolve().parent.parent.parent`).
- Produces: five pytest functions — `test_type_checking_is_recommended`, `test_type_checking_fails_on_warnings`, `test_ruff_select_present`, `test_agents_md_recipes_exist_in_justfile`, `test_actions_are_sha_pinned`. These are collected by `just policy` (Task 2) and by bare `uv run pytest` (the CI `test` job + `just test`).

- [ ] **Step 1: Create the empty package marker**

Create `tests/policy/__init__.py` with **no content** (0 bytes; `D104` is ignored under `tests/**`, and end-of-file-fixer leaves an empty file alone).

- [ ] **Step 2: Create the test suite**

Create `tests/policy/test_gates.py` with exactly this content (verbatim from the validated file):

```python
"""Config-literal pins: gates cannot be silently weakened. Stdlib only."""

import re
import tomllib
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_type_checking_is_recommended() -> None:
    assert PYPROJECT["tool"]["basedpyright"]["typeCheckingMode"] == "recommended"


def test_type_checking_fails_on_warnings() -> None:
    assert PYPROJECT["tool"]["basedpyright"]["failOnWarnings"] is True


def test_ruff_select_present() -> None:
    select = cast("list[str]", PYPROJECT["tool"]["ruff"]["lint"]["select"])
    assert "ALL" in select


def test_agents_md_recipes_exist_in_justfile() -> None:
    """docs-can't-lie: the first `just <recipe>` per fenced invocation is a real recipe."""
    justfile = (ROOT / "justfile").read_text()
    recipes = set(re.findall(r"^([a-z][a-z-]*):", justfile, re.MULTILINE))
    agents = (ROOT / "AGENTS.md").read_text()
    blocks = cast("list[str]", re.findall(r"```.*?```", agents, re.DOTALL))
    referenced: set[str] = set()
    for block in blocks:
        referenced |= set(re.findall(r"just ([a-z][a-z-]*)", block))
    assert referenced <= recipes, f"AGENTS.md names missing recipes: {referenced - recipes}"


def test_actions_are_sha_pinned() -> None:
    """Every third-party `uses:` is a 40-char SHA + a v-prefixed version comment."""
    # SHA + a version comment (v<major>[.minor[.patch]]); our pins carry the action's
    # exact tag. The maintainer re-verifies the comment matches the SHA at bump time
    # via `gh api .../tags`.
    pattern = re.compile(r"uses:\s*\S+@([0-9a-f]{40})\s+#\s*v\d+(\.\d+){0,2}\b")
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in wf.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("- uses:", "uses:")):
                assert pattern.search(stripped), f"unpinned action in {wf.name}: {stripped}"
```

- [ ] **Step 3: Run the suite — expect 5 passed on the current tree**

Run: `uv run pytest tests/policy -q`
Expected: `.....` → **5 passed**. (All five assertions hold today: `recommended` + `failOnWarnings` at pyproject L35–36; `"ALL"` at L50; every fenced `just <recipe>` in AGENTS.md is real; all 12 `uses:` lines are SHA + `# v`.)

- [ ] **Step 4: Lint the new files — expect clean**

Run: `uv run ruff check tests/policy`
Expected: `All checks passed!` (the `tests/**` per-file-ignores already cover `S101`/`PLR2004`/`D103`/`D104`; no inline `# noqa`).

- [ ] **Step 5: Type-check — expect 0 errors, 0 warnings**

Run: `uv run basedpyright`
Expected: `0 errors, 0 warnings, 0 notes`. (If it reports `reportAny` warnings, the docs-can't-lie test was written as a set-comprehension instead of the annotated-loop form above — fix to match Step 2 exactly.)

- [ ] **Step 6: Commit**

```bash
git add tests/policy/__init__.py tests/policy/test_gates.py
git commit -S -m "test(policy): dogfood the gates-can't-be-weakened suite (closes gap #8 sha-pin)"
```

---

### Task 2: `justfile` — `policy` recipe + `ci` member (gap #4)

**Files:**
- Modify: `justfile` (add the `policy` recipe after `test`; add `policy` to the `ci` recipe at line 11)

**Interfaces:**
- Consumes: `tests/policy/` (Task 1).
- Produces: recipe `policy` (so `just policy` and any AGENTS.md fenced `just policy` example resolve to a real recipe); the `ci` recipe now runs `… test policy audit`.

- [ ] **Step 1: Add `policy` to the `ci` recipe**

In `justfile`, replace line 11:

```just
ci: fmt-check lint typecheck test audit
```

with:

```just
ci: fmt-check lint typecheck test policy audit
```

- [ ] **Step 2: Update the `ci` recipe comment for accuracy**

In `justfile`, the `ci` comment currently reads (lines 7–8):

```just
# Mirrors template/justfile.jinja's `ci` (audit is a member — the template chains it,
# and audit is itself a PR-blocking check here via the CI `scan` job's pip-audit step).
```

Replace those two lines with:

```just
# Mirrors template/justfile.jinja's `ci` (policy + audit are members — the template chains
# both; each is also an independent PR-blocking check here — policy via the CI `test` job's
# pytest collection, audit via the CI `scan` job's pip-audit step).
```

(No other comment line changes; there is no enumerated gate list in the comment to sync.)

- [ ] **Step 3: Add the `policy` recipe immediately after the `test` recipe**

In `justfile`, the `test` recipe is:

```just
# Run the template generation + update tests
test:
    uv run pytest
```

Insert directly **after** it (before `# Lint this repo's own tooling` / `lint:`):

```just

# Policy gate: pins the gate config literals (type mode, failOnWarnings, ruff select, Action
# SHAs) so they cannot be silently weakened — not the ignore lists or the recipe bodies.
# Stdlib-only; also auto-collected by `just test`. Mirrors template/justfile.jinja's `policy`.
policy:
    uv run pytest tests/policy
```

- [ ] **Step 4: Verify `just` parses the recipes**

Run: `mise exec -- just --show ci` then `mise exec -- just --show policy`
Expected: `ci: fmt-check lint typecheck test policy audit` (+ its `@echo`); `policy` shows `uv run pytest tests/policy`.

- [ ] **Step 5: Run the recipe — expect 5 passed**

Run: `mise exec -- just policy`
Expected: `uv run pytest tests/policy` → **5 passed**.

- [ ] **Step 6: Commit**

```bash
git add justfile
git commit -S -m "feat(ci): dogfood 'just policy' + chain it into 'just ci'"
```

---

### Task 3: `AGENTS.md` — new Policy-gate section + `ci` gate-list sweep

**Files:**
- Modify: `AGENTS.md` (new `## Policy gate` section after `## Dependency audit`; four `ci` gate-list sweep edits at the `## Run every gate` section)

**Interfaces:**
- Consumes: the `policy` recipe (Task 2) — so the new section's fenced `just policy` example resolves to a real recipe, keeping `test_agents_md_recipes_exist_in_justfile` green.

- [ ] **Step 1: Sweep site — the `+`-form fenced comment**

Replace (in the `## Run every gate` fenced block):

```
just ci   # fmt-check + lint + typecheck + test + audit, then "ci: all gates passed"
```

with:

```
just ci   # fmt-check + lint + typecheck + test + policy + audit, then "ci: all gates passed"
```

- [ ] **Step 2: Sweep site — the prose recipe reproduction**

Replace the sentence fragment:

```
`just ci` is the complete local gate — `ci: fmt-check lint typecheck test audit` ending `@echo "ci: all gates passed"`, with `verify` a bare alias (`verify: ci`). It **mirrors** `template/justfile.jinja`'s `ci`: the template chains `audit` when `enable_dependency_audit` is on (it is), so the faithful maintainer recipe includes it.
```

with:

```
`just ci` is the complete local gate — `ci: fmt-check lint typecheck test policy audit` ending `@echo "ci: all gates passed"`, with `verify` a bare alias (`verify: ci`). It **mirrors** `template/justfile.jinja`'s `ci`: the template chains `policy` and `audit` when `enable_policy_tests`/`enable_dependency_audit` are on (they are), so the faithful maintainer recipe includes both.
```

- [ ] **Step 3: Sweep site — the forward-sync note**

Replace the `**Forward-sync:**` paragraph:

```
**Forward-sync:** when the policy-tests (gap #4) and property-tests (gap #9) layers land, add `policy`/`fuzz` to **both** the `ci` recipe **and** this section, to keep mirroring the template's conditional `ci` (`fmt-check lint typecheck test{% if enable_property_tests %} fuzz{% endif %}{% if enable_policy_tests %} policy{% endif %}{% if enable_dependency_audit %} audit{% endif %}`).
```

with:

```
**Forward-sync:** the policy-tests layer (gap #4) has landed — `policy` is now a `ci` member (see "Policy gate"). When the property-tests layer (gap #9) lands, add `fuzz` to **both** the `ci` recipe **and** this section, to keep mirroring the template's conditional `ci` (`fmt-check lint typecheck test{% if enable_property_tests %} fuzz{% endif %}{% if enable_policy_tests %} policy{% endif %}{% if enable_dependency_audit %} audit{% endif %}`).
```

(The quoted template conditional string is left **verbatim** — it is the template's own literal.)

- [ ] **Step 4: Sweep site — the divergences paragraph**

Replace:

```
Deliberate divergences from `template/justfile.jinja`'s `ci`: **none in the gate list** — `ci: fmt-check lint typecheck test audit`, `verify: ci`, and the `@echo` are exact.
```

with:

```
Deliberate divergences from `template/justfile.jinja`'s `ci`: **none in the gate list** — `ci: fmt-check lint typecheck test policy audit`, `verify: ci`, and the `@echo` are exact.
```

(The "none in the gate list" claim stays true — the template conditionally adds `policy` via `{% if enable_policy_tests %}`, which is on.)

- [ ] **Step 5: Add the new `## Policy gate` section**

In `AGENTS.md`, insert this section **immediately after** the `## Dependency audit` section (i.e. after the Dependency-audit "Deliberate divergences … pin-sync note" paragraph, before `## Add a guardrail layer`).

**Insert the section body only.** The four-backtick fence below is this plan's quoting wrapper (it exists so the inner bash fence can be shown verbatim); it must **not** land in AGENTS.md. After inserting, AGENTS.md must gain exactly **two** triple-backtick runs — the bash fence's open and close — taking it from 16 to **18** (even). Step 6 checks this.

````
## Policy gate (`just policy`)

```bash
just policy   # pins the gate config literals so they cannot be silently weakened (stdlib-only)
```

`just policy` runs `uv run pytest tests/policy` — a stdlib-only (`re`/`tomllib`/`pathlib`) suite pinning this repo's gate **config literals** so they cannot be silently weakened: basedpyright `typeCheckingMode == "recommended"` **and** `failOnWarnings is True`; `"ALL" in ruff select`; the first `just <recipe>` of each **fenced** AGENTS.md example is a real justfile recipe (docs-can't-lie); and every third-party `uses:` is `@<40-hex> # v<ver>` (`test_actions_are_sha_pinned` — this **closes the offline half of the SHA-pin policy**, gap #8). It is a `ci` member (`ci: … test policy audit`) and is also auto-collected by bare `just test` (`uv run pytest`, `testpaths=["tests"]`), so CI enforces it inside the existing `test` job with **no** workflow change.

Changing any of those gates (ruff select, type mode, `failOnWarnings`, an Action pin) requires editing the matching test in `tests/policy/test_gates.py` in the **same commit** — that is the point of the suite. **Scope:** it pins those config *literals* — not the ruff `ignore` / `per-file-ignores` lists (each is separately audited; see "Lint & format this repo"), not the recipe *bodies*, and not the CI workflow that runs the gates (candidate F — see "Run every gate").

Deliberate divergences from `template/tests/…/test_gates.py.jinja`: the **coverage-floor** assertion is dropped (the maintainer has no `[tool.coverage]` / no runtime package — nothing to protect; the `policy` recipe likewise drops `--no-cov`, which is invalid with no `pytest-cov`); a **`failOnWarnings is True`** assertion is added (the template ships none — the maintainer pins the type-gate's teeth explicitly, so the suite guards that pin); and the **docs-can't-lie regex is scoped to fenced code blocks** rather than the whole file. The template's naive whole-doc scan still passes here *today*, but it flips to a hard fail the moment this file names a template-only recipe (`fuzz`/`mutate`) in prose — which gap #9 will do. Fenced-only gates the examples you are told to **run** and lets prose name any recipe freely.

**Two invariants this file must hold** (the test reads AGENTS.md as raw text, and the extractor pairs fences *sequentially*): **(a)** never write a literal triple-backtick run in prose — an odd total mispairs every fence after it and sweeps unrelated prose into a "block"; write "fenced code block", never the delimiter. **(b)** Never write a bare `just <name>` for a non-recipe anywhere, prose included — name it without the `just ` prefix (as `fuzz`/`mutate` are named above). (b) is defence-in-depth: it stops a future (a)-slip from turning into a red gate. The suite also scans `#` comments *inside* fences, so the same rule holds there.

The SHA-pin sub-check overlaps the zizmor job (the security control), so its net-new value is annotation hygiene; the config-literals + docs-can't-lie are the substantive net-new gate. `tests/policy/__init__.py` exists because the maintainer's `tests/` is a package (the template ships no such file). **Known limits:** the recipe allowlist regex matches only `[a-z][a-z-]*` names, so a future parametrized or underscored recipe cited in a fenced example would false-positive (broaden the pattern in the same commit); and nothing here asserts that CI still *runs* the gates (candidate F).
````

- [ ] **Step 6: Fence-parity guard — AGENTS.md must hold an even number of triple-backtick runs**

```bash
python3 -c "import pathlib,sys;n=pathlib.Path('AGENTS.md').read_text().count(chr(96)*3);print('fence runs:',n);sys.exit(n%2)"
```

Expected: `fence runs: 18`, exit 0 (16 before this section + the bash fence's open/close). An **odd** count means a literal triple-backtick run leaked into prose — the extractor will mispair every fence after it and sweep prose into a "block", harvesting non-recipe `just` tokens. Fix the prose before continuing; do **not** "fix" the test. (This is exactly how the first draft of this section failed: 19 runs → `{fuzz, mutate}` → red.)

- [ ] **Step 7: Re-run the *whole* policy suite**

Run: `uv run pytest tests/policy -q`
Expected: **5 passed**. The docs-can't-lie test now scans the new section: its only fenced `just` token is `just policy` (a real recipe as of Task 2), and no bare non-recipe `just` token appears anywhere in the file. Run the whole suite, not the single test — Task 1 Step 3's "5 passed" predates this section and never exercised this path.

- [ ] **Step 8: Sweep verification — no stale gate-list literal remains**

Run: `grep -nE 'test ?\+? ?(policy ?\+? ?)?audit' justfile AGENTS.md`
Expected: every hit shows the `… policy … audit` form; **no** bare `test audit` / `test + audit` remains.

- [ ] **Step 9: Commit**

```bash
git add AGENTS.md
git commit -S -m "docs(agents): document 'just policy' + sweep the ci gate-list sites"
```

---

### Finishing: full verification + PR

- [ ] **Step 1: Full local gate (roomy TMPDIR — the `test` matrix needs it)**

Run: `TMPDIR=/home/user/.cache/kickstarter-test-tmp mise exec -- just ci`
Expected: fmt-check + lint + typecheck + test + **policy** + audit all pass, ending `ci: all gates passed`. (`audit` reaches the network; `policy` runs twice — once auto-collected by `test`, once as the explicit member — both trivially fast.)

- [ ] **Step 2: Pre-commit clean over the whole tree**

Run: `mise exec -- just precommit`
Expected: all hooks pass (new files end in `\n` / are empty; none are `^template/`-excluded; basedpyright on push clean).

- [ ] **Step 3: Confirm the guard rails held**

Run: `git diff --stat main`
Expected: only `docs/superpowers/{specs,plans}/2026-07-07-dogfood-policy-tests*`, `tests/policy/__init__.py`, `tests/policy/test_gates.py`, `justfile`, `AGENTS.md`. **No** `template/`, `test-template.yml`, `pyproject.toml`, `mise.toml`, `uv.lock`, `tests/test_generation.py`, or `CHANGELOG.md`.

- [ ] **Step 4: Clean tree**

Run: `git status --short`
Expected: empty (no lingering `requirements-audit.txt` — the `audit` step `rm`s it on success).

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin chore/dogfood-policy-tests
```

Then open the PR (base `main`) with a body per the pr-descriptions skill. State: zizmor N/A (no workflow touched); CI enforces `tests/policy` inside the existing `test` job (bare `uv run pytest` collects it) with no CI change; closes gap #4 and the offline half of gap #8. **Hand the merge to the operator** (do not merge).

## Self-review notes (author check against the spec)

- Five assertions, coverage-floor dropped, `failOnWarnings` added — matches design D1/D2. ✔
- Fenced-only docs-can't-lie in the annotated-loop (typecheck-passing) form — matches design D-REGEX + the empirical finding. ✔
- `policy` recipe after `test`; `ci: … test policy audit`; `test` stays bare (double-collect accepted) — design D3. ✔
- No CI/dep/mise/CHANGELOG/generation-test change — design D4; `tests/test_generation.py` already covers the template layer. ✔
- `tests/policy/__init__.py` present — design D5. ✔
- All four `ci` gate-list sweep sites (AGENTS.md `+`-form, prose, forward-sync note, divergences) + the justfile recipe — design D6; the broadened acceptance grep catches the `+`-form. ✔
- No `template/` file → no generation-test obligation; no inline `# noqa`; no Action SHA bump. ✔
- **Fence parity**: the inserted section adds exactly two triple-backtick runs (16 → 18, even); no literal delimiter appears in its prose; no bare `just <non-recipe>` token appears anywhere in AGENTS.md. Guarded by Task 3 Step 6. ✔ *(This was the blocker in the first draft: the divergence paragraph wrote the delimiter literally **while describing fenced-only**, taking the count to 19 and failing — on `{fuzz, mutate}` — the very suite it was introducing.)*
- Headline wording scoped to what the suite actually pins (config **literals** — not the ruff ignore lists, recipe bodies, or CI wiring); the docstring says *first* `just <recipe>` per fenced invocation. ✔
