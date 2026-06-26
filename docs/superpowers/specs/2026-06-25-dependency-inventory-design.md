# Design: comprehensive, trustworthy dependency-surface visibility

**Date:** 2026-06-25
**Status:** proposed (awaiting review) — revised after a 5-dimension adversarial spec review
**Scope:** Make every dependency surface — across **both layers** (the maintainer harness
*and* the generated project) — discoverable and trustworthy. The **inventory of record is
in-repo**: a hand-maintained surface-map in `AGENTS.md` plus `just deps`, both
version-controlled and test-asserted. **Renovate is the freshness/automation layer** on
top (it keeps every surface current and provides an independent auto-detected
cross-check), and **`zizmor` is the GitHub Actions pin-enforcement gate** — both already
shipped downstream; the gap is that the maintainer repo runs neither for itself. Concrete
deliverables: a maintainer `renovate.json`, a `just deps` recipe + an "Inspect the
dependency graph" surface-map in both layers, and a maintainer `just deps-template`.
**Evidence-driven** by a deep-research pass (2026-06-25, run `wf_812c2942-714`; 21
sources, 24/25 adversarially-verified claims): Renovate-for-freshness + zizmor-for-Actions
is the prevailing practice (Cilium, Astral), and a bespoke "completeness-guard test" is
**not** — so that is an explicit, documented non-goal.

> **Revision note.** This spec was revised after an adversarial review caught a blocker
> (the first draft crowned Renovate's *out-of-repo, optional* dashboard as "the inventory
> of record") and two CI-breaking landmines (a maintainer `customManager` tracking
> `zizmor`, and Renovate bumping `uv`, each desyncs an existing parity test). The trust
> model is now inverted (in-repo record; Renovate as freshness), and the maintainer
> `renovate.json` is scoped to avoid both desyncs.

## Problem

`python-kickstarter` pins dependencies across many heterogeneous surfaces, and only one of
them (`uv.lock`) is inspectable with a single command today.

| Surface | Maintainer harness | Generated project |
|---|---|---|
| uv / PEP 621 Python deps | `pyproject.toml` + `uv.lock` | `template/pyproject.toml.jinja` (+ generated `uv.lock`) |
| mise tool pins | `mise.toml` `[tools]` | `template/mise.toml.jinja` (+ `gitleaks`) |
| pre-commit hooks | — *(none of its own)* | `template/.pre-commit-config.yaml.jinja` (`rev:` SHAs) |
| GitHub Actions | `.github/workflows/*.yml` (`uses:` SHAs) | `template/.github/workflows/*.jinja` |
| uvx / mise pins in run-steps | `uvx zizmor@…` | `uvx zizmor@/semgrep@/pip-audit@…`, `mise … gitleaks` |

Two concrete gaps:

1. **No single, trustworthy inventory across these surfaces.** `uv tree` shows only the uv
   graph; the rest are visible only by reading individual files, and nothing names *all*
   the places to look.
2. **The maintainer repo has no `renovate.json` at all** — so its own deps drift
   unsupervised. This session's review found `copier 9.15.2→9.16.0`, `ruff 0.15.19→0.15.20`,
   and `pydantic-core 2.46.4→2.47.0` pending, none surfaced. The template ships a
   comprehensive Renovate config *downstream*; the maintainer repo never adopted one for
   itself — a dogfooding gap, like the typecheck/ruff dogfood gaps before it.

## Evidence basis (deep-research, 2026-06-25)

A 5-angle research pass (21 sources; 105 claims; 25 verified by 3-vote adversarial panels
— **24 confirmed, 1 killed**). The workflow's synthesis stage degraded to a placeholder;
the findings below were reconstructed from the run's per-claim verification logs (run
`wf_812c2942-714`), with exact wording recovered for the load-bearing claims — treat the
confidence tags as "verified per-claim," not "from a clean synthesis."

- **Renovate is the de-facto cross-surface *freshness* mechanism, and its dashboard
  doubles as an auto-detected inventory.** [high; 3-0] Native managers for
  `github-actions`, `mise`, and `pre-commit` (the last off by default — the template
  enables it), plus `customManager` regex for ad-hoc pins like `uvx tool@ver`. The
  Dependency Dashboard issue renders a `## Detected Dependencies` section enumerating
  everything its managers detect (the *single killed claim* asserted the dashboard is
  "updates only, not an enumeration"; refuted 0-3 — the enumeration exists). Named
  practice: Cilium uses Renovate with `helpers:pinGitHubActionDigests` + `pinDigests:true`
  as its cross-surface SHA-freshness mechanism ("the prevailing" pattern).
  Sources: `docs.renovatebot.com/modules/manager/{,mise/,pre-commit/}`,
  `/key-concepts/dashboard/` (Renovate source `lib/workers/repository/package-files.ts`),
  `cncf.io` & `cilium.io` CI/CD posts.
- **SBOMs do not cover non-package-manager surfaces.** [high; 3-0] `uv export` covers only
  the Python lockfile graph — "not … GitHub Actions, pre-commit hooks, or mise tools." A
  committed SBOM would give false cross-surface confidence.
  Sources: `docs.astral.sh/uv/concepts/projects/export/`, arxiv SBOM-coverage papers.
- **Actions pin-trust is handled by purpose-built tooling, not bespoke tests.** [high; 3-0]
  `zizmor` enforces SHA pinning (`unpinned-uses`); OpenSSF Scorecard's Pinned-Dependencies
  check and `pinact` cover the same surface. (See the caveat under "Trust model" about
  zizmor's *comment-drift* audit and `--persona=regular`.)
  Sources: `docs.zizmor.sh/audits/`, `github.com/ossf/scorecard`,
  `github.com/suzuki-shunsuke/pinact`.
- **A custom "completeness-guard" test is NOT established practice.** [medium; 2-1] *"Even a
  top-tier project did NOT use an automated completeness-guard test … instead it discovered
  drift via a manual one-off audit … which turned up 68 internal `@main` references that had
  escaped its SHA-pinning."*
  Sources: `cncf.io` CI/CD post, `medium … 100 security projects` survey.

**Conclusion that drives this design:** the mature-project trust model is Renovate
(freshness) + zizmor (Actions enforcement). For an artifact that is "of record" and
"trustworthy," an in-repo, always-present, **test-asserted** surface-map is more
trustworthy than an external, optional dashboard — so the surface-map is the record and
Renovate's auto-detected list is the independent cross-check. A bespoke completeness-guard
test is a deliberate non-goal.

## Goal / success criteria

1. The maintainer repo carries a `renovate.json` so that, **once the Renovate app is enabled
   on the repo** (see Operator preconditions), its uv/mise/Actions surfaces get freshness PRs
   (catching the drift in Problem ②), **scoped to avoid the `zizmor` parity desync and the
   multi-site `uv` desync** (see Design ①).
2. `just deps` exists in **both** layers as `uv tree --frozen` — reads the committed lock,
   no resolve, no network, no lockfile mutation (a bare `uv tree` can re-resolve and rewrite
   `uv.lock`; `--frozen` is what makes the "off the committed lock" contract true and earns
   the recipe its existence over typing `uv tree`).
3. `just deps-template` exists in the **maintainer** repo and prints the *in-development*
   generated project's resolved graph (renders **HEAD/worktree**, not the latest tag — see
   Design ②/③).
4. **Both** layers carry the **dependency surface-map** (the content, not a uniform section
   name): a new `## Inspect the dependency graph` section in the maintainer `AGENTS.md`, and
   the same map folded into the template's existing `## Dependencies` section. Each names
   every surface, the one command to read it, and the trust model (in-repo map + `just deps`
   = record; Renovate = freshness + cross-check; zizmor = Actions enforcement).
5. The template-side surface-map is **toggle-correct** and covered by `tests/test_generation.py`
   assertions — **present-when-on AND absent-when-off** for every gated row (the house
   contract), with **named anchor literals**.
6. The template's existing Renovate config is **verified** to cover every shipped surface —
   changed only if a gap is found (none expected).

## Non-goals (explicitly deferred, with rationale)

- **A completeness-guard test** (fail CI if a pin appears outside an enumerated set of
  files). No proven project relies on one; mature projects accept the residual
  "forgot-to-wire-a-manager" gap and catch it with Scorecard/periodic audits. Its function
  is partly served here for free by the **surface-map ⟷ Renovate Detected-Dependencies
  cross-check** (two independent enumerations that should agree; disagreement is the drift
  signal). The residual gap is in Risks.
- **A committed SBOM / generated inventory doc.** Python-only or scan-based; false
  cross-surface confidence and drift.
- **Freshness/audit *recipes*.** `uv tree --outdated` and the advisory command are
  documented in `AGENTS.md` and run ad hoc; `just deps` stays graph-only. The template
  already ships `just audit` (gated on `enable_dependency_audit`).
- **Changing the *template's* Renovate `uv` handling.** The maintainer config (added here)
  disables `uv` to avoid desyncing its own multi-site `uv` pins (`mise.toml` + the `setup-uv`
  inputs), which no maintainer-side test guards; the *template's* shipped config has the same
  multi-site `uv` pin (plus the `uv_build` floor) but its *rendered* pins **are** checked, by
  `test_generation.py:802`. Reconciling the template's Renovate-vs-uv-pins is a known follow-up,
  out of scope here (this spec adds no new downstream drift — it only adds a maintainer-side
  config).
- **OpenSSF Scorecard / pinact workflows.** zizmor covers Actions pin-trust; Scorecard is a
  possible future layer.
- **A maintainer `just ci` aggregate.** The repo has none; `deps`/`deps-template` are
  standalone, on-demand inspection — not blocking gates.

## Design

### Trust model (the conceptual core — inverted from the first draft)

Three roles, ordered by trustworthiness:

- **Inventory of record (in-repo, always present, testable):** the `AGENTS.md` surface-map
  + `just deps`. Version-controlled, ships with the repo, asserted by generation tests —
  it cannot silently disappear or require an external service.
- **Freshness + independent cross-check:** Renovate. Its managers open update PRs across
  every surface, and its `## Detected Dependencies` dashboard section is a second,
  auto-derived enumeration to reconcile against the hand-maintained map.
- **Enforcement on the riskiest surface:** `zizmor`, already in CI on both layers
  (maintainer `test-template.yml` `zizmor` job; template `scan.yml` under
  `enable_sha_pin_policy`). Its `unpinned-uses` audit enforces SHA pinning under the
  configured `--persona=regular`. **Caveat (verify in implementation):** zizmor's
  SHA-comment-*drift* audit may require a higher persona than `regular`; so the repo's NEVER
  rule ("don't bump a SHA without updating its exact-tag comment") is **not assumed
  auto-enforced** — the surface-map states zizmor enforces *pinning*, and flags comment
  drift only if the persona/audit mapping confirms it.

### Maintainer harness deliverables

**① `renovate.json` (NEW), scoped to avoid the `zizmor` parity desync and the multi-site `uv`
desync.** Verified against the suite: `test_generation.py:797` asserts the maintainer
`uvx zizmor@…` pin equals the rendered `scan.yml` pin (single shared version). Therefore the
maintainer config **omits a `customManager`** — its only `uvx` pin is `zizmor`, which must move
in lockstep with the template, not bumped independently (and a markdown-embedded pin would be
untrackable regardless; see ④/⑤). It also **disables `uv` updates**, but not to keep a parity
*test* green: that test (`test_generation.py:802`) reads the *rendered* template, not the
maintainer's own files, so a maintainer `uv` bump cannot touch it. The real reason is that the
maintainer's `uv` is genuinely multi-site — `mise.toml` plus every `setup-uv version:` input in
`test-template.yml`, with **no** maintainer-side test asserting they agree — so Renovate's
`mise` manager would bump only `mise.toml` and silently desync the workflow inputs. `just` in
`mise.toml` is single-site and bumps freely; `copier` is pinned in `mise.toml` **and** declared
as a `uv` dev dep, but the two sites are mutually consistent and both bump freely. The
`pre-commit` manager is omitted (the harness has no pre-commit config). `uv` is bumped manually
across all sites, as today.

> **Residual risk (eyes open).** Disabling `uv` leaves the most drift-prone, multi-site pin with
> no freshness and no drift detection. The freshness-preserving alternative is a `customManager`
> matching the `setup-uv version:` inputs (datasource `pypi`, depName `uv`) grouped with the
> `mise` manager so both move together — deferred here for the simpler manual bump, but recorded
> as the better long-term option.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "helpers:pinGitHubActionDigests"],
  "lockFileMaintenance": { "enabled": true, "schedule": ["before 4am on monday"] },
  "packageRules": [
    {
      "description": "uv is pinned in mise.toml AND every setup-uv version: input in test-template.yml, with no maintainer-side test asserting they agree. Renovate's mise manager would bump only mise.toml and silently desync the workflow inputs — bump uv manually across all sites instead.",
      "matchDepNames": ["uv"],
      "enabled": false
    }
  ]
}
```

(The Problem-② in-range drift is caught by `lockFileMaintenance` — the weekly `uv.lock`
refresh surfaces `ruff`/`pydantic-core` (and `copier`'s lock entry) even though they stay
within their `pyproject` ranges; the built-in `mise` manager catches `copier`'s exact
`mise.toml` pin and bumps `just`. `config:recommended`'s `pep621` manager only opens PRs for
constraint-*violating* upgrades. `github-actions` + `helpers:pinGitHubActionDigests` keep the
workflow `uses:` pins fresh.)

**② `justfile` — add `deps` and `deps-template`.** `deps-template` must be a shebang recipe
(the file's `set shell := [bash -eu -o pipefail -c]` runs each plain line as a separate
`bash -c`, so a `mktemp` dir would not survive), and must pass **`--vcs-ref HEAD`**: copier
defaults to the latest SemVer tag (`v0.1.0`), so a plain `copier copy .` renders the *released*
template, not the in-development one. (`v0.1.0` == HEAD today, masking this; it breaks the
moment work lands under `[Unreleased]`.) With `ref == HEAD`, copier also folds in the dirty
worktree — exactly what "inspect the in-development template" needs. Two execution hazards the
recipe defuses: it invokes `uvx copier` (not `uv run`) so an incidental stale maintainer
`uv.lock`/`.venv` is never re-synced by the inspection, and it `unset`s `VIRTUAL_ENV`/`UV_PYTHON`
(exporting `UV_PYTHON_DOWNLOADS=automatic`) so copier's copy-time resolve uses the rendered
project's own `>= 3.13` interpreter instead of inheriting the maintainer's 3.11 venv and aborting
the sync — the same interpreter-pin leak `conftest.py`'s `without_interpreter_pins()` scrubs.

```make
# Print the uv-resolved dependency graph from the committed lock (no resolve, no network).
deps:
    uv tree --frozen

# Inspect the in-development generated project's resolved graph: render HEAD/worktree with all
# guardrail toggles on into a throwaway dir, lock it, print the tree. `uvx copier` (not
# `uv run`) keeps this inspection from syncing/rewriting the maintainer's own lock/venv;
# unsetting the maintainer interpreter pin lets the render resolve its own 3.13 toolchain (else
# copier's copy-time `uv sync` inherits the 3.11 venv and aborts); `--skip-tasks` drops the
# heavy copy-time `uv sync` (we only need the lock for `uv tree`). Home-based TMPDIR keeps the
# throwaway on the same filesystem as the uv cache.
deps-template:
    #!/usr/bin/env bash
    set -euo pipefail
    unset VIRTUAL_ENV UV_PYTHON
    export UV_PYTHON_DOWNLOADS=automatic
    export TMPDIR="$HOME/.cache"
    mkdir -p "$TMPDIR"
    dir="$(mktemp -d)"
    trap 'rm -rf "$dir"' EXIT
    uvx copier copy --trust --defaults --vcs-ref HEAD --skip-tasks \
        --data project_name="Deps Probe" \
        . "$dir"
    uv lock --directory "$dir"
    uv tree --frozen --directory "$dir"
```

**③ Test-harness precondition — render HEAD in the generation-test fixture.** `conftest.py`'s
`_render` fixture calls `copier.run_copy(template_root, …)` with **no `vcs_ref`**, so it too
targets the latest tag. New assertions for `deps`/the surface-map would render `v0.1.0`
(which predates them) and **fail** once work lands post-tag. Fix: pass `vcs_ref="HEAD"` in
the `_render` fixture. This is safe today (tag == HEAD → identical render) and is a general
correctness fix — it lets generation tests validate the in-development template (and the
dirty worktree during TDD), not the last release. The roundtrip tests keep their explicit
`vcs_ref="v0.1.0"` (they deliberately test the release→update path). *Flagged for reviewer
attention: this touches the shared fixture, beyond "dependency visibility," but is a
precondition for criterion 5.*

**④ `AGENTS.md` — new `## Inspect the dependency graph` section** (after the lint/format
block). The maintainer map is unconditional (no toggles in this repo):

> The inventory of record is this map + `just deps`. Renovate (`renovate.json`) keeps every
> surface fresh and its Dependency Dashboard `## Detected Dependencies` section is an
> independent cross-check.
>
> | Surface | Pinned in | Read it with |
> |---|---|---|
> | uv / Python deps | `pyproject.toml`, `uv.lock` | `just deps` (`uv tree --frozen`); freshness `uv tree --outdated`; advisories — see below |
> | mise tools | `mise.toml` `[tools]` | read the file *(Renovate `mise` manager tracks `just`/`copier`; `uv` is bump-manually)* |
> | GitHub Actions | `.github/workflows/*.yml` `uses:` (SHA + tag comment) | `grep -rn 'uses:' .github/workflows`; **trust:** the `zizmor` job enforces SHA pinning |
> | uvx tool pins | run-steps (`uvx <tool>@<ver>`) | `grep -rn 'uvx .*@' .github/workflows` *(`zizmor` pin is parity-locked to the template; bump both together)* |
> | generated project's graph | rendered template | `just deps-template` |
>
> Advisories (the harness's deps are all dev, so no `--no-dev`; `pip-audit` is left unpinned —
> a version baked into this markdown would be a tool pin no Renovate manager tracks):
> `uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt && uvx pip-audit -r requirements-audit.txt && rm -f requirements-audit.txt`

**⑤ `CHANGELOG.md` — `[Unreleased] / ### Added`** (additive → next minor): the
`deps`/`deps-template` recipes, the AGENTS surface-map, and the maintainer `renovate.json`.

### Template (shipped) deliverables

**⑥ `template/justfile.jinja` — add an unconditional `deps:` (`uv tree --frozen`)** beside
`lint`/`typecheck`.

**⑦ `template/AGENTS.md.jinja` — extend the existing `## Dependencies` section** with the
surface-map. **Correct toggle gating** (verified against the actual toggles):

| Row / note | Gate |
|---|---|
| uv/Python deps row, `just deps` | unconditional |
| mise tools row (`[tools]` always ships) | unconditional |
| pre-commit `rev:` row (`.pre-commit-config.yaml` ships unconditionally — there is **no** `enable_precommit` toggle) | unconditional |
| GitHub Actions row | unconditional; **zizmor trust note** → `enable_sha_pin_policy` |
| uvx scanner-pins row + gitleaks-as-scanner note | `enable_scanners` |
| advisories note (`just audit` / pip-audit) | `enable_dependency_audit` |
| Renovate lead sentence + every "Renovate … tracks it" parenthetical (the `renovate.json` ships only under `{% if enable_renovate %}`) | `enable_renovate`; **fallback** lead when off: point to `just deps` + this in-repo map |

**⑧ Verify `template/{% if enable_renovate %}renovate.json{% endif %}.jinja`** (the
conditional-name idiom — there is no literal `template/renovate.json.jinja`). It already
carries `config:recommended`, `helpers:pinGitHubActionDigests`, `"pre-commit": {enabled:true}`,
and a `customManager` matching `uvx (semgrep|zizmor|pip-audit)@…`; `gitleaks` is covered by
the mise manager. No change expected; change only if verification finds a gap.

**⑨ `tests/test_generation.py` — assertions** (no new file under `template/`, so the NEVER
rule's file-addition clause is not triggered, but the new behavior is locked per the house
"present-when-on AND absent-when-off" contract):
- **unconditional:** rendered `justfile` contains `deps:` and `uv tree`; rendered `AGENTS.md`
  contains the surface-map — anchor on the section/sub-heading text **and** a load-bearing
  cell literal (e.g. the `mise.toml` row), plus the `pre-commit` row. Assert these in the
  **MINIMAL (all-toggles-off) render too**, so accidental over-gating of an "unconditional"
  row is caught (presence under a full render alone would not prove unconditionality).
- **`enable_scanners`:** a **scanner-unique** literal (e.g. `uvx semgrep@1.167.0`, not a generic
  `uvx …@` shape that `pip-audit`/`zizmor` also match) is present when on, **absent when off**;
  likewise the gitleaks-as-scanner note.
- **`enable_dependency_audit`:** the advisory note (`pip-audit`) present when on, absent off.
- **`enable_sha_pin_policy`:** the GitHub-Actions row's zizmor trust-note literal present when
  on, **absent when off** (render the off-case with `enable_sha_pin_policy=False` and another
  toggle on, mirroring the existing pip-audit both-ways test) — without this, ⑦'s fourth gated
  piece is unguarded and criterion 5 is unmet.
- **`enable_renovate`:** the Renovate lead/`Detected Dependencies` phrasing present when on,
  absent (replaced by the fallback) when off.
- **runtime:** the rendered project's `just deps` exits clean (extends the existing
  install-and-run harness; relies on the `vcs_ref="HEAD"` fixture fix from ③).

## Operator preconditions

- **Renovate freshness requires enabling the app — make it an explicit step.** The inventory of
  record is in-repo (the surface-map + `just deps`), so nothing is hollow if the Renovate app is
  absent — only the *freshness PRs and the auto-detected cross-check* lapse. But those are
  exactly what Goal 1 promises, and **committing `renovate.json` produces zero PRs, zero
  dashboard, and zero cross-check on its own**: the Mend Renovate GitHub App (or a self-hosted
  runner) must be enabled on `maybebyte/python-kickstarter`. Confirm whether it is already
  installed; if not, enabling it is a required step to close Goal 1 (tracked in the Sequence),
  not just a recommendation.

## Migration / release impact

- The template change is **purely additive** (a new recipe + an extended doc section);
  downstreams receive it on `copier update` with no conflicts and **no `_migrations` entry**.
- Lands under `[Unreleased]`; additive → next **minor** (0.1.0 is cut). The maintainer
  `renovate.json`, the recipes, and the `_render` fixture change are maintainer-only.

## Verification strategy

| piece | how it's verified |
|---|---|
| maintainer `renovate.json` | `npx --yes --package renovate@<pin> -- renovate-config-validator` passes (it auto-detects `renovate.json`; there is **no** standalone `renovate-config-validator` npm package — it ships inside `renovate`). Pin the version rather than `renovate@latest`, and note it needs a Node runtime — a dev-only tool in no tracked surface (no `package.json`; `mise.toml` pins no node) |
| no parity desync | rendered-template parity tests `test_generation.py:788`/`:797`/`:802` are unaffected (they read the *rendered* template, not the maintainer config); the maintainer's own `uvx zizmor` pin stays single-version because the config omits a `customManager`, and its multi-site `uv` pins stay in sync because the config disables `uv` |
| `just deps` (both layers) | prints `uv tree --frozen` output; rendered-project run asserted in `test_generation.py` |
| `just deps-template` | renders HEAD/worktree all-guardrails-on (hidden precommit-install helper forced off), locks, prints the tree, cleans up; exit 0 |
| template `deps` recipe + AGENTS surface-map | new present-when-on / absent-when-off `test_generation.py` assertions with named anchors |
| maintainer AGENTS surface-map | prose review; the documented commands run clean ad hoc |
| template Renovate config coverage | manual surface-by-surface check against the Problem table; unchanged unless a gap is found |
| zizmor enforcement | already green (maintainer `zizmor` job; template `scan.yml`) — no change |

## Risks / tradeoffs

- **The deferred guard's residual gap (eyes open).** Renovate, zizmor, and Scorecard only
  see surfaces they are *configured* for; none errors when a **new surface type** appears
  that no manager covers (a stray `npx foo@1.2`, a `Dockerfile FROM …@sha`). The
  surface-map ⟷ Detected-Dependencies cross-check catches some of this; a bespoke guard is
  the only thing that fully closes it. We accept the gap (industry-standard) and rely on
  periodic audit.
- **Red dependency PRs are expected.** With `select=["ALL"]` ruff and basedpyright
  `failOnWarnings=true`, a ruff/basedpyright bump can introduce a new finding that fails
  `just lint`/`typecheck` with zero code change — each such Renovate PR needs a manual fix.
  This is the cost of the freshness layer; consider scheduling/grouping to bound the cadence.
- **Two Renovate configs are intentionally different, not parity-bound.** The maintainer
  config omits the `customManager` and `pre-commit` manager and disables `uv` (all for the
  reasons above); the template's keeps them. There is no parity invariant to enforce — the
  difference is documented here, so the earlier "unenforced parity" concern is moot.
- **`deps-template` render cost.** With `--skip-tasks` the recipe resolves only the lock
  (`uv lock`), skipping copier's copy-time `uv sync` and its bundled-Node download; it still
  fetches and resolves the dependency graph, so it is a several-seconds convenience, not a gate.
- **`_render` fixture change has blast radius.** Pinning the fixture to `vcs_ref="HEAD"`
  changes every generation test's render target. Safe now (tag == HEAD) and correct
  (validate the in-development template), but it is a harness-wide behavioral change to
  call out at review.

## Sequence

Maintainer `renovate.json` → **enable the Renovate app (or confirm it is installed) so the
freshness PRs Goal 1 promises actually appear** → `_render` fixture `vcs_ref="HEAD"` → `just
deps` + `deps-template` recipes → maintainer `AGENTS.md` surface-map → `CHANGELOG` → template
`justfile.jinja` `deps` → template `AGENTS.md.jinja` surface-map (toggle-correct) →
`test_generation.py` present/absent assertions → verify the template Renovate config. The
detailed, commit-by-commit plan is produced next by `writing-plans`.
