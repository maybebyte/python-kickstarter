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
| recommended delta | 38 | `reportUnusedCallResult` ×31, `reportAny` ×7 | subdivision 4 below |

The **272** were categorized by a read-only, max-rigor (double-vote) triage
workflow: 6 clusters partitioning all 272 (0 orphans), every cluster
`agreement: full`, `confidence: high`, **`real_type_defect: 0`** — pure
unknown-ness, two independent root causes (both "consumer fixture parameter left
unannotated"). Validated assumptions: `copier` needs **no stubs** (ships
`py.typed`; the `_render -> Path` boundary contains it) and `types-PyYAML` is
**not required**.

The **38 delta** are mechanical and unambiguous — `reportUnusedCallResult` is bare
`copier.run_copy(...)`/`run_in(...)`/`subprocess.run(...)` statements discarding a
non-`None` result (basedpyright suggests the fix: assign to `_`); `reportAny` is
parsed-config subscripts typed `Any` from `yaml`/`json`/`tomllib`. They carry no
cascade and no hidden-defect risk, so they do **not** warrant a re-triage.

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
   — using the parse-typing pattern below.
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

- **Subdivision 4 — clear the `recommended` delta (38)**:
  - `reportUnusedCallResult` ×31 — prefix `_ = ` to each bare result-discarding
    call (basedpyright's own suggested fix) across `test_generation.py` (19),
    `test_update_roundtrip.py` (11), `conftest.py` (1). No behavior change.
  - `reportAny` ×7 — apply the parse-typing pattern below at the `answers`/`cfg`/
    `ci`/`run_step`/`v` sites (test_generation.py:61, 278, 342, 343×3, 544).

**Parse-typing pattern (shared by A#2 and B#4):** type parsed config at the
boundary so subscripts yield `object`, not `Any` — a small `cast`-based helper,
e.g. `cast("dict[str, object]", yaml.safe_load(text))`, with nested descents using
localized `cast`/`isinstance` narrowing. **No `# type: ignore`.** A natural home
is a tiny helper in each repo's test `conftest.py` (the maintainer's, and — as
extra dogfood — the generated one); the implementation plan picks the minimal
form that drives `reportAny` to 0.

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
| after Subdivision 4 (delta) | **0** (GREEN) |

Template side: after Workstream A, re-render the matrix and run basedpyright
`recommended` on minimal/full/app → all **0**; the maintainer's generation suite
(which runs `basedpyright` and `just ci` on rendered projects) stays green.

Triage assumption checkpoints still apply (after S2: `safe_load`/`json.loads`
*arg* findings clear ⇒ no `types-PyYAML`; no new `reportArgumentType`/
`reportOptionalMemberAccess` ⇒ `RenderFn` shape correct; after S4: zero
copier-attributable `Unknown` ⇒ `py.typed` containment holds).

## Risks / tradeoffs

- **`reportAny` + `cast` can be fiddly** — passing an `Any` expression through
  `cast` must itself not re-trigger `reportAny`; the plan verifies each parse-site
  fix against the count-to-0 oracle rather than assuming an incantation.
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
