# Dogfood dependency-audit (pip-audit) — design (2026-07-03)

## Goal

Run the same dependency-advisory gate the template ships (`enable_dependency_audit`)
on the maintainer repo itself, adapted to the maintainer's actual surface
(`package = false`; every dep under `[dependency-groups] dev`; `tests/` the only
Python; no `src/`; one workflow with per-tool jobs). This closes gap #5 of the
dogfooding-gap audit (`docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md`):
pip-audit currently runs **zero times** on the maintainer while the template
forces it on every downstream. It is the last of the security-adjacent trio
(pre-commit → scanners → dependency-audit), and it slots one step into the `scan`
job the scanners dogfood (gap #2, merged PR #7) just created.

This design was produced from a multi-agent audit and adversarially reviewed
(mirror-fidelity, correctness, scope-consistency), and verified against the live
repo. The gate is **green today** (below).

**Empirical finding — pip-audit is the SUBSTANTIVE maintainer gate (unlike
semgrep).** This is the mirror-image of the scanners result. Verified live:

- `uv export --frozen --no-emit-project --no-hashes --no-dev` → **0 packages**
  (empty). Because `package = false` puts *every* dependency (copier, plumbum,
  pytest, pyyaml, basedpyright, ruff, pre-commit + transitives) under
  `[dependency-groups] dev`, the template's `--no-dev` flag exports nothing, so
  pip-audit would audit 0 packages and pass **vacuously**.
- The same command **without** `--no-dev` → **35 packages** — the real graph.
  (`uv.lock` declares 36; `--no-emit-project` correctly drops the root project.)
- So dropping `--no-dev` is a **forced adaptation, not a weakening**: it flips
  pip-audit from an inert exit-0 into a gate that audits the whole dev+transitive
  graph. Where semgrep stayed a 0-file forward guard, pip-audit is load-bearing.
- Gate runs clean today: the recipe exports 35 pins and `uvx pip-audit@2.10.1`
  prints "No known vulnerabilities found", exit 0 (benign cachecontrol
  cache-deserialization warnings are network-fetch noise).

**Drift note.** The gap-audit doc (gap #5) said "28 packages"; the graph has grown
to 35. The reasoning is unchanged; this spec quotes **35**.

**Scope:** pip-audit only. It reuses the `scan` job's existing checkout +
setup-uv; no new action, workflow, or toggle.

## Decisions

Five forks; all resolve by "mirror the template, diverge only where the
maintainer surface forces it." Two command-content divergences (drop `--no-dev`,
`uvx` pin) are forced; the rest is verbatim mirror.

1. **Drop `--no-dev` (D1, forced).** Recipe + CI both run
   `uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt`
   (no `--no-dev`), auditing the full 35-package graph. Empirically `--no-dev`
   exports 0 packages here (see Goal). `--no-emit-project` is **retained** — it
   is harmless under `package = false` and keeps the export line maximally
   template-shaped (only `--no-dev` is removed).
2. **`uvx pip-audit@2.10.1` in both recipe and CI; NO pyproject dep (D2,
   forced).** Follows the merged scanners "skip the dep for uvx-run tools"
   convention (semgrep/gitleaks/zizmor). The template is internally inconsistent
   (a `pip-audit>=2.10` dev-dep + unpinned `uv run pip-audit` in its justfile, but
   `uvx pip-audit@2.10.1` in its `scan.yml`); the maintainer picks the **uvx**
   side everywhere, keeping all three pin literals byte-identical to the template's
   exact-version site (its `scan.yml`).
3. **Cleanup: mirror the template — 3-line recipe + `.gitignore` entry; NO EXIT
   trap (D3, resolved in review).** The template recipe is three lines (export /
   audit / trailing `rm -f requirements-audit.txt`). Under
   `set shell := [bash,-eu,-o,pipefail,-c]` just runs each line as a separate
   `bash -c`, so the `rm` is skipped when pip-audit fails — and the template's own
   answer is to **gitignore** `requirements-audit.txt` (`.gitignore.jinja:12`),
   leaving the failure-case file to be overwritten on the next run. An EXIT trap
   (`trap 'rm -f …' EXIT`) was considered to force physical removal on failure, but
   it is an **unforced divergence** the template does not have: the only real
   requirement is a clean git tree, which the `.gitignore` entry already
   guarantees. Mirror the template's cleanup exactly; add the `.gitignore` line the
   maintainer currently lacks.
4. **New `## Dependency audit` H2 in AGENTS.md (D4).** Placed immediately after the
   `## Scanning` section (which ends at line 53) and before `## Add a guardrail
   layer` (line 55), using the same 4-block shape (recipe fence / prose /
   divergences / pin-sync). A new peer section is an addition, not a restructuring;
   it mirrors how `## Scanning` was placed after `## Pre-commit`. pip-audit earns
   its own section (own pin, own `--no-dev` story, own 3-site pin-sync list).
5. **pip-audit step goes after `setup-uv`, before `semgrep` (D5).** Preserves the
   template `scan.yml` step order (pip-audit → semgrep → gitleaks); zizmor is
   hoisted to its own maintainer job, so pip-audit-before-semgrep is the faithful
   residual order. It needs `uv` (provided by the preceding `setup-uv`).

**CI placement (the reconciled fork): a new `pip-audit` *step* in the existing
`scan` job — not a standalone `audit` job.** The gap-audit plan (§4/gap#5) said
"standalone `audit` job"; the scanners design and my earlier report said "one step
into the `scan` job." The **step** wins — it is consistent with *both* the
template layout (pip-audit is a sibling step of semgrep+gitleaks inside `scan.yml`,
never its own job) *and* the merged gap #2 precedent (the maintainer folded the
whole out-of-band security cluster into one `scan` job). A standalone job would
duplicate checkout + setup-uv, cold-start its own uv cache, and diverge from both
— added surface for zero benefit (GitHub Actions already shows per-step pass/fail,
so failure attribution survives). pip-audit doesn't need the job's `fetch-depth: 0`
(it reads `uv.lock` from the tree) but inherits it harmlessly — cosmetic, not a
reason to split. The gap-audit plan's standalone-job note predates the scanners
dogfood and is **superseded**.

## Wiring

### `justfile`

Add an out-of-band `audit` recipe (chained into no other recipe — there is no
`ci` recipe to fold it into, exactly like `scan`). The export line is byte-identical
to the template's minus `--no-dev`; the pip-audit line uses the `uvx` pin; the
trailing `rm -f` and 3-line form are byte-identical to `template/justfile.jinja:36-39`.
A maintainer-style header comment is added above `audit:` (surface convention):

```just
# Out-of-band dependency vulnerability audit: pip-audit over the FULL locked graph.
# `--no-dev` is dropped (unlike the template): package=false puts every dep in the
# dev group, so the template's --no-dev would export 0 packages and pass vacuously.
# Enforced in CI by the `scan` job, not a `ci` recipe (there is none).
audit:
    uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
    uvx pip-audit@2.10.1 -r requirements-audit.txt
    rm -f requirements-audit.txt
```

### `.gitignore`

Add `requirements-audit.txt` (the maintainer `.gitignore` lacks it; the template
ships it at `.gitignore.jinja:12`). This keeps the tree clean when a failed
pip-audit run skips the recipe's `rm` line — the template's own cleanup story:

```gitignore
# pip-audit's temp export (`just audit`); rm'd on success, gitignored so a failed run leaves a clean tree.
requirements-audit.txt
```

### `.github/workflows/test-template.yml`

Insert ONE step into the existing `scan` job, after the `setup-uv` step and before
the `semgrep` step (preserving template step order). No new `uses:`, no `GH_TOKEN`,
no `fetch-depth` change, no `uv sync` — it reuses the job's
`actions/checkout@9c091bb… # v7.0.0` (`fetch-depth: 0`, `persist-credentials:
false` — required by the sibling gitleaks step, harmlessly inherited) and
`astral-sh/setup-uv@fac544c… # v8.2.0` (`version: "0.11.23"`, `enable-cache:
true`). The two command lines are byte-identical to the recipe's (minus the local
`rm`, which the ephemeral runner does not need — mirroring the template `scan.yml`).
**The `--no-dev` drop applies here too, not just to the local recipe** — this CI
step is the PR-blocking enforcer, so if *it* kept `--no-dev` the gate would pass
vacuously while `just audit` looked fine:

```yaml
      - name: pip-audit
        run: |
          uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
          uvx pip-audit@2.10.1 -r requirements-audit.txt
```

### `AGENTS.md`

Add a peer `## Dependency audit` H2 after `## Scanning`, 4-block shape mirroring it:

````markdown
## Dependency audit

```bash
just audit   # out-of-band dependency vulnerability audit: pip-audit over the full locked graph
```

`just audit` exports the fully-resolved lockfile
(`uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt`) and
runs `uvx pip-audit@2.10.1 -r requirements-audit.txt`. It is out-of-band (chained
into no recipe), but CI enforces it: the `pip-audit` step in the `scan` job of
`.github/workflows/test-template.yml` is a blocking PR gate. Unlike semgrep — which
scans 0 files here — pip-audit is the **substantive** dependency gate: it audits the
real ~35-package dev+transitive graph (copier / pytest / ruff / basedpyright /
pre-commit / plumbum / pyyaml + transitives), because **`--no-dev` is dropped**.
Never restore `--no-dev`: `package = false` puts every dep in the dev group, so
`--no-dev` would export 0 packages and pass vacuously. `requirements-audit.txt` is
`rm`'d on success, gitignored, and lingers (harmlessly) only after a failed run.
pip-audit is the one **non-hermetic** step in the `scan` job — it queries the
OSV/PyPI advisory DB, so this gate can turn red on a newly-published CVE (or an
advisory-DB outage) independent of any code change; a `--frozen` **export** failure
instead means `uv.lock` is stale (re-lock), distinct from a pip-audit non-zero (a
CVE). pip-audit runs via `uvx` (no pyproject dep, like semgrep/zizmor).

Deliberate divergences from the template's dependency-audit layer: `--no-dev` is
dropped (above); pip-audit runs via `uvx pip-audit@2.10.1` in both the recipe and
CI with **no** pyproject dep (the template adds `pip-audit>=2.10` to its dev group
and runs `uv run pip-audit` locally); it is folded into `test-template.yml`'s
`scan` job as a step (the template ships it in a standalone `scan.yml`); and it is
out-of-band, not a `just ci` dependency (the template makes `audit` gating — the
maintainer has no `ci` recipe).

Because nothing here re-derives the pin (no Renovate; the generation drift test
reads only the *rendered* downstream), **bump every literal by hand, against the
template.** pip-audit (`2.10.1`) has three maintainer sites — the `just audit`
recipe, the `pip-audit` step in `test-template.yml`, and the prose above — synced
to `template/.github/workflows/…scan.yml….jinja` (the only exact-version template
site; the template justfile uses unpinned `uv run pip-audit` and template pyproject
floors `pip-audit>=2.10`). No `mise.toml` or `pyproject.toml` pip-audit literal
exists (uvx-run, unlike gitleaks). **Sync only the pin *value* — never the export
flags:** the template's `uv export` keeps `--no-dev`, but the maintainer must not
(it exports 0 packages here — see above), so a mechanical sync against the template
would silently neuter the gate. (Mirrors the semgrep/gitleaks pin-sync note and the
pre-commit "bump both `rev:` pins together" rule.)
````

### `mise.toml` / `pyproject.toml`

**No change** to either. pip-audit runs via `uvx pip-audit@2.10.1` (isolated,
pinned inline), never mise-installed and never a pyproject dep — the semgrep/zizmor
uvx convention. Only gitleaks needs a mise pin (no uvx path). This is a deliberate
divergence from `template/pyproject.toml.jinja:44` (`pip-audit>=2.10`).

## Documented divergences (mirror-except-where-surface-differs)

- **Drop `--no-dev`** — `package = false` makes the template's `--no-dev` export 0
  packages (vacuous); dropping it audits the real 35-package graph. *Forced.*
- **`uvx pip-audit@2.10.1`, no pyproject dep** — the uvx-run-tools convention
  (semgrep/gitleaks/zizmor); the template uses a dev-dep + `uv run pip-audit`
  locally but `uvx pip-audit@2.10.1` in CI. Maintainer is uvx everywhere. *Forced
  by convention.*
- **A `pip-audit` step in `test-template.yml`'s `scan` job**, not a standalone
  `scan.yml` — mirrors the merged scanners fold (one workflow / per-tool layout);
  reuses that job's checkout + setup-uv.
- **Out-of-band, not a `ci` dependency** — the template makes `audit` a `ci` dep
  (a gating layer); the maintainer has no `ci` recipe, so `audit` lands exactly
  like `just scan` (out-of-band, CI-enforced).
- **AGENTS.md pin-sync note** — the maintainer has no Renovate and no self-parity
  test, so the pin is manually synced; mirrors the scanners/pre-commit governance.
- **Unconditional root files** — no `{% if enable_dependency_audit %}` guards to
  reproduce (root files are not `.jinja`); no `copier.yml` change.

## Acceptance

Run pip-audit locally first (it has never run on this repo; a real advisory would
turn the PR red):

```bash
just audit    # exports 35 pins, uvx pip-audit@2.10.1 → "No known vulnerabilities found", exit 0
```

- **Non-vacuity:** the export file contains 35 `==` pins, not 0; and
  `uv export … --no-dev` returns 0 while the same command without `--no-dev`
  returns 35 (both re-runnable) — proving the drop-`--no-dev` adaptation is
  load-bearing.
- **Clean tree:** after `just audit` (including on a pip-audit non-zero),
  `git status` is clean because `requirements-audit.txt` is gitignored.
- **zizmor stays green:** the new step adds no `uses:` / no `GH_TOKEN`, so
  `uvx zizmor@1.26.1 --persona=regular .` passes over the edited workflow (all
  actions still SHA-pinned with exact-tag comments).
- **Generation matrix green** (`just test`): no `template/` file is touched, so no
  generation test inspects the maintainer pip-audit surfaces, and
  `test_tool_version_pins_have_no_drift` (which excludes pip-audit) still passes.
- **Pin-sync:** `grep -rn 'pip-audit@' justfile .github/workflows/test-template.yml
  AGENTS.md` returns `2.10.1` at exactly 3 sites, byte-identical to the template
  `scan.yml`; `mise.toml` and `pyproject.toml` contain no pip-audit literal.
- **Lint/format/typecheck** unaffected (no Python touched): `just lint`,
  `just fmt-check`, `just typecheck` green.

No `test_generation.py` change is owed (root files, not `template/`). **No
CHANGELOG `[Unreleased]` entry and no version tag** — this touches zero `template/`
files, so it is a maintainer-harness change, not a template release (identical to
the scanners dogfood).

## Out of scope / tracked follow-up

- **Aggregate `just ci` (gap #3)** — the maintainer still has no `ci` target;
  `audit` stays out-of-band. If gap #3 later lands, decide then whether to chain
  `audit` (the template does); do not invent a `ci` recipe here.
- **Root-vs-template pin-parity test** — a real governance gap (the pin is
  unguarded here), but it belongs to gap #4 (policy-tests); covered in the interim
  by the AGENTS.md manual-sync note.
- **EXIT-trap cleanup** — considered and rejected (D3): an unforced divergence the
  template does not have; the `.gitignore` entry already keeps the tree clean.
  Trivial to revisit if physical-absence-on-failure ever becomes a hard requirement.

## Explicit no-touch (guard rails)

- `template/**`, `copier.yml`, `tests/test_generation.py`, `CHANGELOG.md`,
  `README.md`, `docs/superpowers/**` (beyond this spec + its plan).
- The existing `scan`-job steps (semgrep, mise-action, gitleaks) and the other CI
  jobs (`test`, `zizmor`, `typecheck`, `lint`) — the only edit to
  `test-template.yml` is INSERTING the new pip-audit step.
- `mise.toml` / `pyproject.toml` — no pip-audit literal (uvx convention).
- The zizmor `1.26.1` pin and the gitleaks `8.30.1` mise pin — untouched.

## Files touched (maintainer root only)

`justfile` (new `audit` recipe), `.github/workflows/test-template.yml` (one new
step in `scan`), `AGENTS.md` (new `## Dependency audit` section), `.gitignore`
(add `requirements-audit.txt`).

## Endorsed decisions (verified in review — do not reopen)

`--no-dev` empirically exports 0 packages (drop it); the full graph is 35 packages
and pip-audit is green today (exit 0); `uvx pip-audit@2.10.1` matches the template's
only exact-version site; the pip-audit step reuses the `scan` job's checkout +
setup-uv (no new action / token / sync); step order pip-audit → semgrep → gitleaks
mirrors the template; cleanup mirrors the template (3-line recipe + `.gitignore`),
not an EXIT trap; the mirror is ROOT-only, so no generation test, CHANGELOG, or tag
is owed.
