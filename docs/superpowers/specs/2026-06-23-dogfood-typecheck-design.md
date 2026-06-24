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
- **C4–C5 (7 × `reportAny`) — NOT mechanical (`needs-attention`).** A *uniform*
  fix backfires under `recommended`: a blanket `dict[str, object]` on the
  nested-descent sites (`cfg["extends"]`, `ci["jobs"]["ci"]["steps"]`) trips
  `reportIndexIssue`/`reportOperatorIssue`, and `cast("dict[str, Any]", …)` trips
  `reportExplicitAny` (a `recommended` rule *outside* the 38). The fix is
  per-site *truthful* types (Subdivision 4b): `dict[str, object]` where the test
  only does membership/equality (`answers`), precise `TypedDict`s where it descends
  into structure (`cfg`, `ci`), and `NotRequired` keys where the real data is
  heterogeneous (workflow `steps`). A real latent fragility surfaced as a
  by-product — `test_generation.py:344` subscripts `run_step["env"]` unchecked, and
  that block renders only under `enable_property_tests` — and the honest recipe
  **resolves** it with an explicit `assert "env" in run_step` (a checked
  precondition), rather than the dishonest alternative of declaring `env` required
  to make the subscript quietly type-check.

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

## Plan-time verification correction (2026-06-23)

Writing the implementation plan, the maintainer remediation was run **end-to-end**
on an isolated `git archive HEAD` copy (not just the 38-delta in isolation, as the
original draft was). That overturned three specifics in this design; the corrections
are folded inline above and the
[implementation plan](../plans/2026-06-23-dogfood-typecheck.md) is authoritative:

1. **`RenderFn` param is `Mapping[str, object]`, not `dict[str, object]`.** The
   original invariance reasoning was backwards — `dict` is invariant, so a
   `dict[str, object]` param rejects `MINIMAL` (`dict[str, str | int | bool]`) with
   24 `reportArgumentType`. Covariant `Mapping` accepts it and is the truthful
   read-only contract. (Subdivision 1.)
2. **Subdivision 4a is 36 sites, not 31.** Typing `render`/`project` *unmasks* 5
   discarded-result calls (`test_generation.py` 98, 109, 180, 268, 506) that
   basedpyright could not flag while their types were `Unknown`. (Subdivision 4a.)
3. **Workstream A must flip the generated policy test** `test_type_checking_is_strict`
   → `recommended`, or the raised bar breaks every full render's `just ci` (the
   generated `ci` recipe depends on `policy`). (Workstream A#2.)

The corrected walk — 310 → 43 → 7 → 0, all four matrix renders 0, runtime green — is
fully reproduced; no claim below rests on composition or assumption any more.

## Design

### Workstream A — template (define the shipped bar)

1. `template/pyproject.toml.jinja` line 95: `typeCheckingMode = "strict"` →
   `"recommended"`. Update the adjacent line-31 comment (the version-coupling
   rationale holds — arguably more so, since `recommended` tracks *all* rules).
2. In the generated policy test — template source
   `template/tests/{% if enable_policy_tests %}policy{% endif %}/test_gates.py.jinja`
   — make two coupled edits (both verified). **(a)** Flip the self-policy:
   `test_type_checking_is_strict` → `test_type_checking_is_recommended`, asserting
   `== "recommended"`. This is **mandatory**, not cosmetic: the generated `justfile`'s
   `ci` recipe depends on `policy`, so leaving the assertion at `"strict"` breaks
   every full render's `just ci` (the maintainer's `test_full_combo_gate_green` /
   `test_all_toggles_on_passes_full_gate` / `test_policy_layer`). The policy test
   pins what the gate *is*; after the flip that is `recommended`. **(b)** Fix the one
   `reportAny` at `test_gates.py:20` — `select = PYPROJECT["tool"]["ruff"]["lint"]["select"]`
   is inferred `Any`; wrap it `cast("list[str]", …)` (the honest-`cast` shape; `select`
   is genuinely a list of ruff rule codes) and add `from typing import cast`.
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
failOnWarnings = true              # DECLARE the gate's teeth (recommended defaults it
                                   # true, but make it explicit so a future mode/version
                                   # drift under the <1.40 cap can't silently un-fail it)
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
  from collections.abc import Callable, Mapping
  from typing import TypeAlias
  RenderFn: TypeAlias = Callable[[Mapping[str, object], Path], Path]
  ```

  The shape is **load-bearing and exact** (corrected at plan time — see "Plan-time
  verification correction"): param **`Mapping[str, object]`**, which is *covariant*
  in its value type and so accepts `MINIMAL` (inferred `dict[str, str | int | bool]`);
  a `dict[str, object]` param does **not** — `dict` is *invariant*, so it raises
  `reportArgumentType` on every call site (verified end-to-end). `Mapping` is also
  the truthful contract: `render` only reads its answers. Return exactly `Path` (a
  looser `object`/`Path | None` flips silent `Unknown`s into loud
  `reportOptionalMemberAccess`/`reportAttributeAccessIssue`); not bare
  `Callable`/`Callable[..., Path]` (ellipsis re-leaks `Unknown`). Also widen the
  inner helper to `def _render(data: Mapping[str, object], dst: Path) -> Path:` and
  annotate the fixture `def render(template_root: Path) -> RenderFn:`.

- **Subdivision 2 — annotate `render: RenderFn` at all 39 consumer defs in
  `tests/test_generation.py`** (clears the bulk of the 272-finding cascade). Add `RenderFn` to
  the `from tests.conftest import run_in` import. Def-lines: 46, 70, 90, 102, 112,
  118, 123, 133, 138, 169, 177, 188, 198, 210, 224, 233, 242, 261, 276, 285, 295,
  308, 335, 350, 364, 371, 395, 411, 421, 430, 443, 474, 489, 498, 510, 525, 557,
  572, 579. Once `render: RenderFn`, `project = render(...)` is `Path` and the
  whole `Path`→`str`→sink chain types out. Mirrors `test_update_roundtrip.py`.

- **Subdivision 3 — annotate `template_root: Path`** in
  `test_precommit_install_task_runs` (line 151; clears the cascade's independent
  root). The one test that bypasses the fixture and calls `copier.run_copy`
  directly. Folded into the same commit as Subdivisions 1–2 (one boundary change).

- **Subdivision 4 — clear the `recommended` delta (38), re-triaged into 5
  clusters** (read-only double-vote; dispositions above). Land the mechanical part
  first, then the `reportAny` part with dedicated care:
  - **4a — `reportUnusedCallResult` ×36 (clusters C1–C3, mechanical):** prefix
    `_ = ` to each bare result-discarding call. **31 are visible at baseline; 5 more
    (`test_generation.py` lines 98, 109, 180, 268, 506) are *unmasked* once
    Subdivision 2 types `render`/`project`** — basedpyright can't flag a discarded
    `Unknown`. `test_generation.py` (24): lines 98, 109, 114, 115, 120, 135, 140,
    147, 148, 156, 172, 180, 193, 268, 367, 423, 436, 462, 482, 506, 575, 582, 583,
    584. `test_update_roundtrip.py` (11): lines 21, 51, 63, 72, 74, 80, 114, 126,
    137, 143, 148. `conftest.py` (1): the bare `copier.run_copy` in `_render` (line
    40 after Subdivision 1). `_` is exempt from `reportUnusedVariable`; no behavior
    change.
  - **4b — `reportAny` ×7 (clusters C4–C5, `needs-attention`):** in
    `test_generation.py`, add the typing import + precise `TypedDict`s and `cast`
    at each parse boundary (verified honest recipe below). Sites: 61 (`answers`),
    278 (`cfg`), 342 + 343×3 (`ci`/`run_step`/`s`/`s.get`), 544 (`v` from
    `re.findall`). The recipe models the data *truthfully* (no over-claimed keys or
    value types) and **resolves** the L344 unchecked subscript with an explicit
    `assert "env" in run_step` — turning the latent KeyError into a checked
    precondition. Do **not** rewrite L344 to `.get("env", {})` (that silently
    changes the test's semantics).

**Parse-typing recipe (verified honest; shared by A#2 and B#4b).** The types must
model the *real* data — not a blanket `cast` to `Any`/`object`, and not an
over-claim that silences a finding by asserting a falsehood. In
`test_generation.py`:

```python
from typing import NotRequired, TypedDict, cast

class _Step(TypedDict):
    run: NotRequired[str]            # workflow steps are heterogeneous: `uses:` steps
    env: NotRequired[dict[str, str]] # (checkout/setup-uv) carry neither key
class _CiJob(TypedDict):
    steps: list[_Step]
class _CiWorkflow(TypedDict):
    jobs: dict[str, _CiJob]

# `pre-commit` is hyphenated → functional form is mandatory (class syntax can't).
# These keys ARE required: cfg is a single object the test itself generates and asserts.
_PreCommit = TypedDict("_PreCommit", {"enabled": bool})
_Renovate = TypedDict("_Renovate", {"extends": list[str], "pre-commit": _PreCommit})
```

then `cast` at the boundaries, and make the `env` precondition explicit:

```python
answers = cast("dict[str, object]", yaml.safe_load(...))  # L61 — values are mixed
                                                          #       str/int/bool, not all str
cfg     = cast("_Renovate",   json.loads(...))            # L278
ci      = cast("_CiWorkflow", yaml.safe_load(...))        # L342 — narrows L343's chain
run_step = next(s for s in ci["jobs"]["ci"]["steps"] if s.get("run") == "just ci")
assert "env" in run_step                                  # L344 was an UNCHECKED subscript;
assert run_step["env"]["HYPOTHESIS_PROFILE"] == "ci"      #       this surfaces the contract
... for v in cast("list[str]", re.findall(r"\d+\.\d+\.\d+", line))   # L544 (group-less → list[str])
```

**No `# type: ignore`, and no type that lies.** Casting *from* `Any` never trips
`reportUnnecessaryCast`; the string-literal cast targets resolve under the file's
existing `from __future__ import annotations`. `NotRequired` `run`/`env` reflects
that most steps lack them, and the explicit `assert "env" in run_step` is what
narrows the `NotRequired` key so `reportTypedDictNotRequiredAccess` is satisfied
*honestly* (by a checked precondition) rather than suppressed by a false
required-key claim. **Empirically confirmed:** this honest recipe reaches the
identical **310 → 272** with **zero new rule names** — modeling reality costs
nothing here. (Rejected as dishonest *and* unnecessary: `dict[str, str]` for
`answers` over-narrows mixed values; required `_Step.env` asserts a key real steps
lack purely to dodge the diagnostic that guards L344.) The template's single
generated `reportAny` (A#2) takes the same honest-`cast` shape — audit it against
the actual rendered value, not an assumed one.

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
| after Subdivisions 1–3 (render/copier boundary typed) | 43 |
| after Subdivision 4a (`_ = ` ×36) | 7 |
| after Subdivision 4b (`reportAny` recipe) | **0** (GREEN) |

The **whole walk is now empirically verified end-to-end** (plan time): on an
isolated `git archive HEAD` copy with the real gate, the counts ran exactly
310 → 43 → 7 → 0, and the affected tests still pass at runtime (the `assert "env"
in run_step` holds; casts are no-ops). Subdivisions 1–3 are collapsed into one
"type the render/copier boundary" step because Subdivision 1 alone clears nothing
and the three are one logical change; the residual 43 after it is 36
`reportUnusedCallResult` (31 visible + 5 unmasked) + 7 `reportAny`. See "Plan-time
verification correction".

Template side: after Workstream A, re-render the matrix and run basedpyright
`recommended` on minimal/full/app → all **0**; the maintainer's generation suite
(which runs `basedpyright` and `just ci` on rendered projects) stays green.

Triage assumption checkpoints still apply (after S2: `safe_load`/`json.loads`
*arg* findings clear ⇒ no `types-PyYAML`; no new `reportArgumentType`/
`reportOptionalMemberAccess` ⇒ `RenderFn` shape correct; after S4: zero
copier-attributable `Unknown` ⇒ `py.typed` containment holds).

## Risks / tradeoffs

- **`reportAny` was the non-mechanical risk — now retired honestly.** The naive
  fixes backfire (`reportExplicitAny`/`reportIndexIssue`/
  `reportTypedDictNotRequiredAccess`), so the recipe uses per-site *truthful*
  `TypedDict`s + `cast`; **empirically verified** (310 → 272, zero new rule names),
  not assumed. The L344 unchecked subscript is **resolved** (explicit `assert "env"
  in run_step`), not deferred — see the integrity-audit note below.
- **`RenderFn` precision is load-bearing** (Subdivision 1).
- **Upgrade churn** — `recommended` tracks *every* basedpyright rule, so a minor
  bump is likelier to redden the tree; the `<1.40` cap contains it (bump
  deliberately).
- **39 annotation + 36 discard-prefix edits** must be exact; the per-step count
  drop makes any miss immediately visible.

## Integrity audit — does this game the checker?

The bar: reach zero by *fixing* type safety, never by silencing it. The recipe was
adversarially audited against a four-part "gaming" taxonomy — **suppression**
(`# type: ignore`/rule-disable/mode-lowering/surface-narrowing), **dishonest types**
(a `cast`/`TypedDict` asserting what the data doesn't guarantee), **test-weakening**
(`_ =` hiding a result that should be asserted), and **gate dishonesty** (config/CI
that only looks enforced) — by an independent read-only review panel *and* an
empirical count oracle.

**Verdict: honest, with three small fixes (folded in above).** The bulk is the
*opposite* of gaming: it clears findings by **supplying true type information the
checker was missing** (`RenderFn` is `_render`'s exact signature; `template_root` is
genuinely a `Path`) and by making **already-unused** returns explicit (`_ =`, where
`check=True` already raises on failure — verified that every result-asserting site
is captured into a name and excluded). No `# type: ignore`, no rule downgrade, no
mode lowering (`strict → recommended` is a *raise*); `exclude` drops only Jinja/cache
paths (**zero** `.py` files) and the gate runs the full `tests/` surface. The three
corrected spots, each a place the first recipe asserted a convenient falsehood:

| spot | was (mild gaming) | now (honest) |
|---|---|---|
| `answers` value type | `cast("dict[str, str]")` — false (`coverage_floor` int, `enable_*` bool) | `cast("dict[str, object]")` |
| `_Step.run`/`env` | **required** — false (`uses:` steps lack both) → silenced the rule guarding L344 | `NotRequired` + explicit `assert "env" in run_step` |
| `failOnWarnings` | inherited from the `recommended` default | declared `= true` |

Modeling reality **cost nothing**: the honest recipe reaches the *identical*
**310 → 272, zero new rule names**, and the `_Step` fix turns the latent L344
KeyError into a checked precondition rather than papering over it. Both the triage
and the audit were reproduced by the count oracle on an isolated copy of the
committed tree.

## Sequence

Workstream B (config + dev-dep) → Subdivisions 1–3 → 4a → 4b
(watching 310 → 43 → 7 → 0) → recipe → CI job → AGENTS.md → Workstream A (template
bar). The detailed, commit-by-commit plan is produced next by `writing-plans`.
