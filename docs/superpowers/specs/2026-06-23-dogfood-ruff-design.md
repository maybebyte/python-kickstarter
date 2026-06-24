# Design: dogfood the full ruff config (`select=["ALL"]`) on the maintainer harness

**Date:** 2026-06-23
**Status:** proposed (awaiting review)
**Scope:** lint + format only — bring the template's full-fledged ruff config
(`select=["ALL"]` + curated, *audited* ignores) onto the maintainer repo's own
`tests/` harness, declare a version-capped `ruff` dev-dep, wire `just
lint`/`fmt`/`fmt-check`, drive the harness to **0 ruff findings honestly**, and
enforce it in CI. This is the deferred follow-up the typecheck dogfood spec named
on record ("that spec will use the same triage-workflow rigor"). The template
already ships `select=["ALL"]` by default, so **there is no template-side change.**

## Problem

`python-kickstarter` is a Copier template. It ships a comprehensive ruff config to
every generated project, but **the maintainer repo never ran that config on its own
harness.** Today `just lint` is `uv run ruff check .` with **no `[tool.ruff]`
section anywhere** — so it runs only ruff's default `E`/`F` rules (it reports *"All
checks passed!"* — green, but hollow). There is no declared `ruff` dependency (it
resolves ambiently, the same reproducibility hole basedpyright had pre-dogfood), no
`fmt`/`fmt-check` recipe, and **no lint/format step in CI at all** (the
`test-template.yml` jobs are pytest, `zizmor`, and `typecheck`). The only Python
surface is the four-file `tests/` harness (`conftest.py`, `test_generation.py`,
`test_update_roundtrip.py`, `__init__.py`); there is no `src/`, and `template/` is
Jinja (`*.jinja`), never linted as Python.

This mirrors the typecheck gap exactly, and the remedy mirrors the typecheck
remedy: adopt the comprehensive bar, declare the dep, make the harness pass it with
**no suppressions**, add recipes + a hardened CI job, document it.

## Goal / success criteria

1. The maintainer's `pyproject.toml` carries an inline `[tool.ruff]` config:
   `select=["ALL"]`, the template's shared tuning (line-length 100, mccabe ≤10,
   pylint limits, pydocstyle google, isort, format = double-quote + docstring-code),
   adapted to the harness (`target-version="py311"`, `known-first-party=["tests"]`,
   no `src/`), and a **minimal, fully-audited ignore set** (config **N** below).
2. `ruff check .` and `ruff format --check .` both pass with **zero findings** over
   the harness.
3. `ruff` is a **declared, version-capped dev dependency** (`ruff>=0.15,<0.16`,
   matching the template and the repo's cap-and-bump-deliberately philosophy).
4. `just lint` / `just fmt` / `just fmt-check` run it locally; **CI enforces**
   `ruff check` + `ruff format --check` on every push/PR.
5. **No inline `# noqa`** anywhere in the final state (the three existing ones are
   removed), no `select` lowering, no surface-narrowing. Every committed `ignore` /
   `per-file-ignore` entry is **load-bearing and truthfully justified** — reach zero
   by *fixing* defects + an audited ignore set, never by silencing a fixable one.
6. The basedpyright `recommended` gate stays green after the ruff fixes
   (cross-gate compatibility — **verified**).

## Non-goals

- **No template-side change.** The template already ships `select=["ALL"]` by
  default (`ruff_ruleset: all`); nothing to raise. (Contrast the typecheck dogfood,
  which *also* raised the shipped bar `strict → recommended`.)
- The `just ci` / `just check` aggregate recipe and `mise` tool pins for the
  linters (the typecheck spec deferred these; they remain deferred).
- A pytest test that shells out to ruff — the CI job is the durable lock.
- Changing the *shipped* ruleset choice or the `ruff_ruleset` toggle.

## Migration / release impact

This changes only the **maintainer** repo, not what generated projects are held to,
so there is **no downstream blast radius and no `_migrations` entry**. Like the
typecheck dogfood it should still land **before the first release tag**, alongside
that change, so `v0.1.0` ships a maintainer harness that fully dogfoods both gates.

## Verified findings basis

Real runs of **ruff 0.15.19** (`uvx --from 'ruff>=0.15,<0.16' ruff`) over the
actual `tests/` surface, against a *bare maximal* config (`select=["ALL"]` + the
shared tuning, **empty** `ignore` and `per-file-ignores`). Every count below was
reproduced deterministically; the full walk to 0 and the cross-gate check were run
end-to-end on `git archive HEAD` throwaway copies.

### The maximal RED baseline

| measurement | count |
|---|--:|
| `ruff check` respecting `noqa` (the literal repo state) | **163** |
| `ruff check --ignore-noqa` (the honest "must-resolve" count; we remove all `noqa`) | **166** |
| `ruff format --check` | 2 files would reformat |

166 findings across **17 rules**. Histogram: `S101`×112, `D103`×23, `COM812`×6,
`E501`×5, `PT018`×3, `S603`×2, `TC003`×2, `D205`×2, `RUF100`×2, `S607`×2, `D104`×1,
`D202`×1, `UP013`×1, `PLC0415`×1, `PLR2004`×1, `D403`×1, `PLW1510`×1.

### How the partition was derived (the triage workflow)

A dynamic, read-only triage **workflow** (persisted at
`…/workflows/scripts/ruff-dogfood-triage-*.js`) ran 74 agents over the 17 rule
clusters: a per-rule **disposition proposer** → **3 diverse-lens adversarial
skeptics** (hidden-defect / behavior-change / justification-honesty,
default-to-skeptical) → **reconcile** → **synthesis** → a **3-dimension audit panel**
(completeness / gaming-taxonomy integrity / count-sanity). The adversarial pass
materially changed two proposals (it earned its keep):

- **`E501`** — proposer wanted to ignore it ("formatter leaves these lines
  intact"); two skeptics **empirically refuted** that — `ruff format` reflows all 5.
  Flipped to **fix-via-formatter**.
- **`S603`** — kept the ignore but **rewrote a justification built on false
  premises** ("fires unconditionally") into the honest one (a trust-discriminating
  rule; the harness's subprocess inputs are literal command lists).

The audit panel then flagged three synthesis errors, which a **deterministic count
oracle** (not an agent) confirmed and corrected:

| synthesis claim | oracle verdict |
|---|---|
| `RUF100` / `PT018` are *manual* | **autofixable** — `RUF100 --fix` strips the stale `noqa` cleanly; `PT018` splits under `--unsafe-fixes` |
| `PLW1510` is *autofix* | **manual** — it survives `ruff check --fix --unsafe-fixes` |
| baseline "164/166" ambiguity | **166** (`--ignore-noqa`), 163 literal |
| `per-file` blanket `"D"` + `E501` ignored *and* "fixed" | inert — resolved by config **N** (specific `D103`/`D104`, fix the rest) |

## Config mechanism

Inline `[tool.ruff]` in the maintainer `pyproject.toml` (mirrors the shipped shape
and the basedpyright dogfood). ruff naturally skips `template/` (its files are
`*.jinja`, not `*.py`); an `extend-exclude = ["template"]` is a count-neutral parity
guard (there is no `.py` under `template/` today) recommended for forward-safety,
mirroring basedpyright's `exclude=["template"]`.

## Design

### Config (the committed `[tool.ruff]`, config **N** — minimal-honest)

Every `ignore` entry below is load-bearing (it fires on the surface and is
genuinely inappropriate to enforce there) or a documented formatter conflict.
Nothing is inherited un-audited from the template.

```toml
[tool.ruff]
line-length = 100
target-version = "py311"            # requires-python floor (template uses chosen python_version)
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
    "S607",     # …invoked by name on PATH (shutil.which over REQUIRED_TOOLS); absolute paths regress portability
    "D103",     # test functions are self-documenting via descriptive names
    "D104",     # tests/ is an (empty) package marker
]

[tool.ruff.format]
quote-style = "double"
docstring-code-format = true
```

**Divergence from the template prior (each audited):**
- **ADD `S603`/`S607`** to `tests/**` — this harness shells out to the dev toolchain;
  the shipped template's generated tests never do, so the prior never needed them.
- **Specific `D103`/`D104`** instead of the template's blanket `"D"` — we *ignore*
  missing-docstring (tests needn't have docstrings) but *fix* docstring-formatting
  (`D205`/`D202`/`D403`): "docstrings are optional on tests, but well-formed if present."
- **Drop the template's global `E501`** — we fix the 5 sites via the formatter
  rather than inherit a blanket ignore.
- **Omit `ANN`/`INP001`/`SLF001`** (in the template's `tests/**`) — 0 findings here
  (the harness is fully type-annotated, `tests/` is a real package, no flagged
  private access). We hold the harness *higher* than the template's tests where we
  already satisfy it.

### Dependency

Add `"ruff>=0.15,<0.16"` to `[dependency-groups].dev` (via `uv add --dev`);
`uv.lock` regenerates. Cap-and-bump-deliberately — `ALL` tracks every rule ruff
adds, so a minor bump can redden a green tree.

### Recipes (`justfile`) — mirror the template's

```make
lint:
    uv run ruff check .

fmt:
    uv run ruff format .
    uv run ruff check --fix .

fmt-check:
    uv run ruff format --check .
```

(`lint` replaces the config-less recipe; it is now config-driven.)

### CI — `.github/workflows/test-template.yml`

A dedicated `lint` job mirroring the existing `typecheck`/`zizmor` hardening exactly
(SHA-pinned actions with exact-tag comments, `persist-credentials: false`, pinned
`uv` `0.11.23`), single runner (lint/format are interpreter-version-independent):

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
      - run: uv sync
      - name: Lint (ruff check, select=ALL)
        run: uv run ruff check .
      - name: Format check (ruff format --check)
        run: uv run ruff format --check .
```

### Docs — maintainer `AGENTS.md`

A `## Lint & format this repo` subsection after the `## Type-check this repo` block:
`just lint` / `just fmt-check` run ruff `select=["ALL"]` over `tests/` (config-derived,
audited ignores) — the same full ruleset the template ships; CI-enforced.

## Remediation — the verified partition (166 → 0)

**Ignores (config N) remove 147 raw findings** — `S101`(112), `D103`(23), `S603`(2),
`S607`(2), `D104`(1), `PLR2004`(1), `COM812`(6); `ISC001` carries 0 findings
(formatter-conflict guard). The naive residual would be 19 (166−147), but ignoring
`S603`/`S607` turns one more stale `noqa` into a `RUF100` finding, so the **measured
residual is 20** — a config-dependent interaction the oracle accounts for.

**Autofix cluster — `ruff check --fix --unsafe-fixes .` then `ruff format .`
(clears 16):**
| rule | sites (real-repo lines) | fix |
|---|---|---|
| `E501`×5 | test_generation.py:81,343,389,461,519 | formatter reflows |
| `TC003`×2 | test_generation.py:8; test_update_roundtrip.py:7 | `Path` → `TYPE_CHECKING` block (file has `from __future__ import annotations`) |
| `UP013`×1 | test_generation.py:32 | `_PreCommit` functional→class; **`_Renovate` correctly stays functional** (hyphenated `pre-commit` key) |
| `D202`×1 | conftest.py:30 | drop blank line after docstring |
| `D403`×1 | test_generation.py:263 | capitalize first word (`semgrep`→`Semgrep`) |
| `PT018`×3 | test_generation.py:339,437; test_update_roundtrip.py:93 | split composite `assert a and b` |
| `RUF100`×3 | conftest.py:56; test_update_roundtrip.py:21,98 | strip stale `noqa` (S603/S607 now ignored) |

**Manual (clears the last 4):**
| rule | site | fix |
|---|---|---|
| `D205`×2 | test_generation.py:393,417 | add a one-line summary + blank line (description retained) |
| `PLC0415`×1 | test_generation.py:173 | hoist function-local `import copier` to the top third-party group |
| `PLW1510`×1 | test_update_roundtrip.py:98 | add explicit `check=False` (the `assert ci.returncode == 0` is the real check; the line's stale `noqa` is already stripped by the `RUF100` autofix step above) |

**Latent items surfaced as by-products (all resolved by the fixes above):** the
implicit subprocess `check=` at roundtrip:98, a dead `noqa` half (roundtrip:21,
`RUF100`), and an import-outside-top-level smell (test_generation.py:173).

## Verification strategy (ruff is the oracle)

Verified end-to-end on `git archive HEAD` throwaway copies with the real gate:

| step | expected count |
|---|--:|
| baseline RED (`--ignore-noqa`) | **166** |
| after landing config N (ignores) | **20** |
| after `ruff check --fix --unsafe-fixes .` + `ruff format .` | **4** |
| after the 3 manual fixes | **0** (GREEN), `ruff format --check` clean |

**Cross-gate (verified):** after the N fixes, `uv run basedpyright`
(`recommended`) returns **0 findings** — the ruff dogfood does not redden the
typecheck gate. (`TC003`'s `Path`→`TYPE_CHECKING` is safe under
`from __future__ import annotations`; the `UP013` rewrite preserves both
`TypedDict`s.)

## Integrity audit — does this game the checker?

The bar: reach zero by *fixing* lint defects + a justified, audited ignore set,
never by silencing a fixable one. Audited (by the workflow's gaming-taxonomy panel
and the count oracle) against four failure modes:

- **Suppression** — none: **zero inline `# noqa`** in the final state (the three
  existing ones are *removed*, not relied on); no `select` lowering; `extend-exclude`
  drops only Jinja (zero `.py`).
- **Dishonest ignore** — each entry is truthful: `COM812`/`ISC001` are ruff's own
  documented formatter conflicts; `S101`/`PLR2004`/`S603`/`S607`/`D103`/`D104` are
  category-inappropriate for a controlled pytest harness, scoped `per-file` to
  `tests/**` (so a future `src/` is still held to the full bar). We deliberately do
  **not** inherit the template's non-firing ignores (the rejected config M), which
  would be exactly the "inherited assumption" the maximal posture exists to avoid.
- **Test-weakening** — none: `PT018` splits make failures *more* precise;
  `PLW1510`'s `check=False` is behavior-preserving (the assertion is the real check);
  `D205`/`D403` touch only docstring text; `PLC0415`/`TC003`/`UP013` are
  import/type-form moves. The `S101` ignore was adversarially checked for asserts
  that smuggle a fixable defect (e.g. side-effecting calls stripped under `-O`):
  none — `run_in` defaults `check=True`, so the subprocess raises before the assert.
- **Gate dishonesty** — the CI job runs the full `ruff check .` + `ruff format
  --check .`; `just lint`/`fmt-check` are the same commands.

Modeling reality cost nothing extra here: the honest minimal config reaches the
identical 0 and keeps the harness held to the strongest defensible bar.

## Risks / tradeoffs

- **Upgrade churn** — `select=["ALL"]` tracks every rule ruff adds; a minor bump can
  redden the tree. The `<0.16` cap contains it (bump deliberately) — identical to
  the template's own rationale.
- **`D205` fixes invent summary lines** — a slightly more invasive edit than the
  others (2 test docstrings), accepted under config N's "well-formed if present"
  stance.
- **Two gates now share a `from __future__ import annotations` dependence** —
  `TC003`'s `TYPE_CHECKING` move relies on it; it is already present in both touched
  files. (A future file without it would need it before `TC003` autofix is safe.)
- **The triage workflow is reusable** — re-run it (or just the oracle) on the next
  ruff minor bump to re-derive the partition.

## Sequence

Config + dev-dep (`uv add --dev ruff`, inline `[tool.ruff]` = config N) → RED (166)
→ land ignores (→20) → autofix `--unsafe-fixes` + format (→4) → 3 manual fixes (→0)
→ recipes → CI `lint` job → `AGENTS.md`. The detailed, commit-by-commit plan is
produced next by `writing-plans`.
