# Design: adopt basedpyright `recommended` everywhere (template + maintainer dogfood)

**Date:** 2026-06-23
**Status:** proposed (awaiting review)
**Scope:** type-checking only — move *both* the shipped template and the
maintainer repo onto basedpyright `typeCheckingMode = "recommended"`, and make
each pass it. The ruff/format dogfood and the aggregate `just ci` gate remain a
deliberately deferred follow-up (see Non-goals).

## Problem

`python-kickstarter` is a Copier template. It ships a strict basedpyright gate to
every project it generates, but **the maintainer repo never ran one on its own
`tests/` harness** — no config, no declared dep, no recipe, no CI step (CI runs
only `uv run pytest`). The maintainer's only type-checkable surface is the
four-file test harness under `tests/` (there is no `src/`); `template/` is Jinja
and is never analyzed.

While closing that gap we found the template ships `typeCheckingMode = "strict"`,
which is an explicit *down-pick* from basedpyright's own default, `recommended`.
The strictness ladder is `off · basic · standard · strict · recommended · all`;
`recommended` enables **all** rules (minor ones as warnings, with
`failOnWarnings = true` so CI still fails), `all` is identical rule-wise but every
finding is an error. **Decision (this spec): adopt `recommended` for both
surfaces** — it raises the bar to the tool's own default while *preserving the
dogfood symmetry* (the maintainer is held to exactly what it ships). We do **not**
choose `all`: rule-wise it equals `recommended`, and the error/warning split buys
nothing here.

## Goal / success criteria

1. The template ships `typeCheckingMode = "recommended"`, and **every generated
   project passes it** out of the box.
2. The maintainer's own `tests/` passes `basedpyright` `recommended`
   (`pythonVersion = "3.11"`, the `requires-python` floor) with **zero findings**
   (errors *and* warnings — `failOnWarnings` gates them).
3. `basedpyright` is a **declared, version-capped dev dependency** of the
   maintainer repo (closing the reproducibility hole; it resolves only ambiently
   today).
4. A `just typecheck` recipe runs it locally; **CI enforces it** on every push/PR.
5. **No `# type: ignore` / no per-rule downgrades** — both surfaces are made
   genuinely clean, not silenced. Choosing `recommended` and then disabling its
   rules would defeat the purpose.

## Non-goals (deferred follow-ups)

- **Ruff / format dogfood** for the maintainer (root `[tool.ruff]`, making
  `tests/` pass it, the `ruff` dev-dep, `just lint`/`fmt-check`). The existing
  config-less `just lint` is untouched. **On record:** that spec will use the
  same triage-workflow rigor applied to the type findings here.
- The `just ci` / `just check` aggregate and `mise` tool pins for the linters.
- A pytest test that shells out to basedpyright — the CI job is the durable lock.
- Changing the strictness *ceiling* (`all`) or adopting `baseline`.

## Migration / release impact

Bumping the shipped mode changes what every generated project is held to. Because
the repo carries **no tags and has no downstream consumers yet**, **no
`_migrations` entry is required** — but this must land **before the first
release** (a later `strict → recommended` flip on existing downstreams could break
their CI and *would* need a gated migration).

## Verified findings basis

Real runs of `basedpyright 1.39.8`, `pythonVersion 3.11`, imports resolved against
the actual `.venv`.

### Maintainer `tests/` under `recommended`: 310 findings (all warnings)

| group | count | rules | disposition |
|---|--:|---|---|
| render/template_root cascade (the `strict` set, now warnings) | 272 | `reportUnknown{Variable,Member,Argument,Parameter}Type`, `reportMissingParameterType` | subdivisions 1–3 below (already triaged) |
| recommended delta | 38 | `reportUnusedCallResult` ×31, `reportAny` ×7 | re-triaged into 5 clusters; subdivision 4 below |

The **272** were categorized by a read-only, max-rigor (double-vote) triage
workflow: 6 clusters partitioning all 272 (0 orphans), every cluster
`agreement: full`, `confidence: high`, **`real_type_defect: 0`** — pure
unknown-ness, two independent root causes (both "consumer fixture parameter left
unannotated"). Validated assumptions: `copier` needs **no stubs** (ships
`py.typed`; the `_render -> Path` boundary contains it) and `types-PyYAML` is
**not required**.

The **38 delta** were then re-triaged by the same read-only double-vote workflow
(cartographer → per-cluster skeptic + predictor → reconcile → synthesize), which
split them into **5 clusters** and *overturned* an initial "all mechanical" read:

- **C1–C3 (31 × `reportUnusedCallResult`) — mechanical.** Bare result-discarding
  calls; the fix is the diagnostic's own suggestion, prefix `_ = `. Safe because
  every site either defaults `check=True` (a nonzero exit *raises*, so the
  behavior-under-test is "it did not raise") or runs purely for a filesystem side
  effect, and no flagged site reads the return. Both votes `all-mechanical`, high
  confidence, zero net-new findings.
- **C4–C5 (7 × `reportAny`) — NOT mechanical (`needs-attention`).** The obvious
  fixes *backfire* under `recommended`: `dict[str, object]` trades `reportAny` for
  `reportIndexIssue`/`reportOperatorIssue` at every subscript, and even
  `cast("dict[str, Any]", …)` trips `reportExplicitAny` (a `recommended` rule
  *outside* the 38). The verified fix needs precise `TypedDict`s + targeted `cast`s
  (Subdivision 4b). A real latent fragility surfaced as a by-product:
  `test_generation.py:344` subscripts `run_step["env"]` unchecked, and that block
  renders only under `enable_property_tests` — the recipe *preserves* current
  behavior (declares `env` required, leaves L344 untouched) and **flags it for
  human review** rather than silently changing semantics.

**Empirically confirmed (count oracle).** Applying the full C1–C5 recipe to an
isolated copy of the committed tree drove basedpyright `recommended` from **310 →
272** — all 38 delta findings cleared, **zero new rule names** introduced (checked:
no `reportExplicitAny`/`reportIndexIssue`/`reportTypedDictNotRequiredAccess`/
`reportUnnecessaryCast`/`reportUnusedVariable`), the residual 272 being exactly the
cascade baseline. So the original judgment was *partly* correct: mechanical for 31,
wrong for the 7 `reportAny`.

### Generated projects under `recommended`: essentially clean

| project | findings |
|---|--:|
| minimal | 0 |
| app | 0 |
| full | **1** — a single `reportAny` in the generated `tests/policy/test_gates.py` |

The shipped scaffold is already `recommended`-clean except one line in the
policy-test layer, so the downstream blast radius is **one fix**.

### Config mechanism (verified via basedpyright docs / context7)

`[tool.basedpyright]` inline in `pyproject.toml` and a standalone
`pyrightconfig.json` are both first-class (precedence: `pyrightconfig.json` wins
if both exist). `typeCheckingMode` accepts the six-rung ladder above. basedpyright
**auto-detects `.venv`** in the project root (no `venvPath`/`venv` needed).
**Decision: inline `[tool.basedpyright]`** in the maintainer `pyproject.toml`,
mirroring the shipped shape.

## Design

### Workstream A — template (define the shipped bar)

1. `template/pyproject.toml.jinja` line 95: `typeCheckingMode = "strict"` →
   `"recommended"`. Update the adjacent line-31 comment (the version-coupling
   rationale holds — arguably more so, since `recommended` tracks *all* rules).
2. Fix the single `reportAny` in the generated policy test — template source
   `template/tests/{% if enable_policy_tests %}policy{% endif %}/test_gates.py.jinja`
   — using the verified parse-typing recipe below (B#4b).
3. Generation tests: no test pins the `"strict"` string, and the existing
   `run_in(project, "uv", "run", "basedpyright")` (test_generation.py:120) already
   runs the checker on a rendered project — it now exercises `recommended` and
   stays green after fix #2. Add a teeth-check asserting the generated
   `pyproject.toml` contains `typeCheckingMode = "recommended"`, so a silent
   revert is caught.

### Workstream B — maintainer (mirror the bar; close the gap)

**Config — `pyproject.toml`, inline:**

```toml
[tool.basedpyright]
typeCheckingMode = "recommended"   # basedpyright's default; matches what we ship
pythonVersion = "3.11"             # the requires-python floor
include = ["tests"]                # the only Python surface; there is no src/
exclude = ["template", "**/__pycache__", "**/.venv"]  # template/ is Jinja, never Python
reportMissingImports = "error"
```

**Dependency:** add `"basedpyright>=1.39,<1.40"` to `[dependency-groups].dev`
(`uv add --dev`). The `<1.40` cap matches the template and the repo's
cap-and-bump-deliberately philosophy — doubly warranted under `recommended`, which
tracks every rule basedpyright adds.

**Remediation — four subdivisions (annotation-only; no suppressions):**

- **Subdivision 1 — define `RenderFn` in `tests/conftest.py`** (prerequisite;
  clears 0). basedpyright resolves fixtures by parameter *name* and never infers a
  consumer param's type from a same-named fixture, so a nameable, importable type
  must exist first:

  ```python
  from collections.abc import Callable
  from typing import TypeAlias
  RenderFn: TypeAlias = Callable[[dict[str, object], Path], Path]
  ```

  The shape is **load-bearing and exact**: param `dict[str, object]` (a narrower
  `dict[str, str]` raises `reportArgumentType` — `MINIMAL` carries int/bool
  values); return exactly `Path` (a looser `object`/`Path | None` flips silent
  `Unknown`s into loud `reportOptionalMemberAccess`/`reportAttributeAccessIssue`);
  not bare `Callable`/`Callable[..., Path]` (ellipsis re-leaks `Unknown`). As
  hygiene, also annotate the fixture `def render(template_root: Path) -> RenderFn:`.

- **Subdivision 2 — annotate `render: RenderFn` at all 39 consumer defs in
  `tests/test_generation.py`** (clears **269** of the cascade). Add `RenderFn` to
  the `from tests.conftest import run_in` import. Def-lines: 46, 70, 90, 102, 112,
  118, 123, 133, 138, 169, 177, 188, 198, 210, 224, 233, 242, 261, 276, 285, 295,
  308, 335, 350, 364, 371, 395, 411, 421, 430, 443, 474, 489, 498, 510, 525, 557,
  572, 579. Once `render: RenderFn`, `project = render(...)` is `Path` and the
  whole `Path`→`str`→sink chain types out. Mirrors `test_update_roundtrip.py`.

- **Subdivision 3 — annotate `template_root: Path`** in
  `test_precommit_install_task_runs` (line 151; clears **3**). The one test that
  bypasses the fixture and calls `copier.run_copy` directly. Independent root.

- **Subdivision 4 — clear the `recommended` delta (38), re-triaged into 5
  clusters** (read-only double-vote; dispositions above). Land the mechanical part
  first, then the `reportAny` part with dedicated care:
  - **4a — `reportUnusedCallResult` ×31 (clusters C1–C3, mechanical):** prefix
    `_ = ` to each bare result-discarding call. `test_generation.py` (19): lines
    114, 115, 120, 135, 140, 147, 148, 156, 172, 193, 367, 423, 436, 462, 482, 575,
    582, 583, 584. `test_update_roundtrip.py` (11): lines 21, 51, 63, 72, 74, 80,
    114, 126, 137, 143, 148. `conftest.py` (1): line 36. `_` is exempt from
    `reportUnusedVariable`; no behavior change.
  - **4b — `reportAny` ×7 (clusters C4–C5, `needs-attention`):** in
    `test_generation.py`, add the typing import + precise `TypedDict`s and `cast`
    at each parse boundary (verified recipe below). Sites: 61 (`answers`), 278
    (`cfg`), 342 + 343×3 (`ci`/`run_step`/`s`/`s.get`), 544 (`v` from `re.findall`).
    Carry the L344 unchecked-subscript flag for reviewer awareness; do **not**
    rewrite it to `.get("env", {})` (that silently changes the test's semantics).

**Parse-typing recipe (verified; shared by A#2 and B#4b).** The fix is *precise
types*, not a blanket `cast` to `Any`/`object`. In `test_generation.py`:

```python
from typing import TypedDict, cast

class _Step(TypedDict):
    run: str
    env: dict[str, str]      # both keys REQUIRED: total=False trips
                             # reportTypedDictNotRequiredAccess on run_step["env"]

class _CiJob(TypedDict):
    steps: list[_Step]

class _CiWorkflow(TypedDict):
    jobs: dict[str, _CiJob]

# `pre-commit` is hyphenated → functional form is mandatory (class syntax can't):
_PreCommit = TypedDict("_PreCommit", {"enabled": bool})
_Renovate = TypedDict("_Renovate", {"extends": list[str], "pre-commit": _PreCommit})
```

then `cast` at the three boundaries (+ the `re.findall` element):

```python
answers = cast("dict[str, str]", yaml.safe_load(...))   # L61
cfg     = cast("_Renovate",      json.loads(...))        # L278
ci      = cast("_CiWorkflow",    yaml.safe_load(...))    # L342 — narrows L343's whole chain
... for v in cast("list[str]", re.findall(r"\d+\.\d+\.\d+", line))   # L544
```

**No `# type: ignore`.** Casting *from* `Any` never trips `reportUnnecessaryCast`;
the string-literal cast targets resolve under the file's existing
`from __future__ import annotations`. Rejected (empirically worse under
`recommended`): `dict[str, Any]` → `reportExplicitAny`; `dict[str, object]` →
`reportIndexIssue`; `total=False` → `reportTypedDictNotRequiredAccess`. The
template's single generated `reportAny` (A#2) takes the same precise-`cast` shape,
verified against the same oracle at implementation.

**Recipe — `justfile`:**

```make
# Type-check this repo's own tooling (the tests/ harness) under basedpyright.
typecheck:
    uv run basedpyright
```

**CI — `.github/workflows/test-template.yml`:** a dedicated `typecheck` job
(single runner — typecheck is interpreter-version-independent via the configured
`pythonVersion`), mirroring the existing `zizmor` job's hardening (SHA-pinned
actions with exact-tag comments, `persist-credentials: false`, pinned uv):

```yaml
  typecheck:
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
      - name: Type-check (basedpyright recommended)
        run: uv run basedpyright
```

**Docs — maintainer `AGENTS.md`:** note `just typecheck` (basedpyright
`recommended` over `tests/`) is part of the local gate and CI-enforced.

## Verification strategy (basedpyright is the oracle)

`failOnWarnings` under `recommended` makes the CLI exit non-zero until **0
findings**. Predicted maintainer count at each step:

| step | expected count |
|---|--:|
| baseline (RED) | 310 |
| after Subdivision 1 (type defined) | 310 |
| after Subdivision 2 (39 `render` params) | 41 |
| after Subdivision 3 (`template_root`) | 38 |
| after Subdivision 4a (`_ = ` ×31) | 7 |
| after Subdivision 4b (`reportAny` recipe) | **0** (GREEN) |

The 38-delta half of this path is **empirically verified** in isolation (committed
tree, delta recipe only: 310 → 272, zero new rule names); the cascade half (S1–S3)
is orthogonal — `reportUnusedCallResult`/`reportAny` are independent of `render`'s
type — so the steps compose to 0.

Template side: after Workstream A, re-render the matrix and run basedpyright
`recommended` on minimal/full/app → all **0**; the maintainer's generation suite
(which runs `basedpyright` and `just ci` on rendered projects) stays green.

Triage assumption checkpoints still apply (after S2: `safe_load`/`json.loads`
*arg* findings clear ⇒ no `types-PyYAML`; no new `reportArgumentType`/
`reportOptionalMemberAccess` ⇒ `RenderFn` shape correct; after S4: zero
copier-attributable `Unknown` ⇒ `py.typed` containment holds).

## Risks / tradeoffs

- **`reportAny` was the non-mechanical risk — now retired.** The naive fixes
  backfire (`reportExplicitAny`/`reportIndexIssue`/`reportTypedDictNotRequiredAccess`),
  so the recipe uses precise `TypedDict`s + `cast`; it is **empirically verified**
  (310 → 272, zero new rule names) rather than assumed. The one residual is the
  flagged `test_generation.py:344` unchecked subscript, left behavior-preserving
  for human review (a latent KeyError if the conditional `env:` block is ever
  dropped — not introduced by this change).
- **`RenderFn` precision is load-bearing** (Subdivision 1).
- **Upgrade churn** — `recommended` tracks *every* basedpyright rule, so a minor
  bump is likelier to redden the tree; the `<1.40` cap contains it (bump
  deliberately).
- **39 + 31 mechanical edits** must be exact; the per-step count drop makes any
  miss immediately visible.

## Sequence

Workstream A (template bar) → Workstream B config + dev-dep → Subdivisions 1→2→3→4
(watching 310 → 310 → 41 → 38 → 0) → recipe → CI job → AGENTS.md. The detailed,
commit-by-commit plan is produced next by `writing-plans`.
