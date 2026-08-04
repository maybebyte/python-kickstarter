# Design: comprehensive, trustworthy dependency-surface visibility

**Date:** 2026-06-25
**Status:** proposed (awaiting review) — revised after a 5-dimension adversarial spec review,
then amended 2026-08-04 after an adversarial re-verification of the Renovate design (see
"Amendment note")
**Scope:** Make every dependency surface — across **both layers** (the maintainer harness
*and* the generated project) — discoverable and trustworthy. The **inventory of record is
in-repo**: a hand-maintained surface-map in `AGENTS.md` plus `just deps`, both
version-controlled and test-asserted. **Renovate is the freshness/automation layer** on
top (it keeps every surface current and provides an independent auto-detected
cross-check), and **`zizmor` is the GitHub Actions pin-enforcement gate** — both already
shipped downstream. `zizmor` already runs in both layers (including the maintainer repo's
`test-template.yml`); the only maintainer-side gap is that it carries no `renovate.json`. Concrete
deliverables: a maintainer `renovate.json`, a `just deps` recipe + an "Inspect the
dependency graph" surface-map in both layers, and a maintainer `just deps-template`.
**Evidence-informed** by a deep-research pass (2026-06-25, run `wf_812c2942-714`; 21 sources;
per-claim adversarial verification): Renovate-for-freshness is a documented pattern (Cilium),
zizmor is purpose-built tooling for the Actions surface, and a bespoke "completeness-guard
test" is not established practice — so that is an explicit, documented non-goal, justified
primarily by its engineering cost and disclosed residual gap (its "not established practice"
leg rests on a single `[medium; 2-1]` claim — see Evidence).

> **Revision note.** This spec was revised after an adversarial review caught a blocker
> (the first draft crowned Renovate's *out-of-repo, optional* dashboard as "the inventory
> of record") and two desync landmines: a maintainer `customManager`
> tracking `zizmor` would break an existing parity test (CI-breaking), and Renovate bumping
> `uv` would *silently* desync the unguarded multi-site `uv` pins (no test catches it). The trust
> model is now inverted (in-repo record; Renovate as freshness), and the maintainer
> `renovate.json` is scoped to avoid both desyncs.

> **Amendment note (2026-08-04).** Only deliverable ③ (`vcs_ref="HEAD"` in the `_render`
> fixture) has landed, via PR #4. Everything else here is still unbuilt, and in the interim
> gaps #1–#5 and #8 of the dogfood-gap audit landed — invalidating several of this spec's
> factual premises (the harness *does* now have a pre-commit config, a `just ci` aggregate,
> a `just audit` with a pinned `pip-audit`, and five `uvx` pins rather than one). An
> adversarial re-verification pass (2026-08-04; four claim reviews, each independently
> re-derived and then refuted, plus a completeness critique) also found **two defects in the
> Renovate design that would have shipped**:
>
> 1. **The `packageRules` entry was under-scoped and would have caused the very desync it
>    was written to prevent.** `matchDepNames: ["uv"]` matches depName only. Renovate's
>    `mise` manager surfaces `mise.toml`'s `uv` pin as depName `uv`, but its `github-actions`
>    manager natively extracts `astral-sh/setup-uv`'s `with: version:` input as depName
>    `astral-sh/uv`. The original rule would therefore have silenced the `mise.toml` side
>    while leaving all five workflow inputs free to bump. Corrected to
>    `matchPackageNames: ["astral-sh/uv"]`, which matches both (both carry that packageName)
>    and does not touch the action's own digest pin (packageName `astral-sh/setup-uv`).
> 2. **There is no Renovate manager named `uv`.** The manager reading `pyproject.toml` +
>    `uv.lock` is `pep621`. A top-level `"uv": {…}` key is an *invalid configuration option*,
>    which aborts the whole repository run — not a silent no-op. This spec never wrote that
>    key, but the gap-audit's restatement of this bullet ("Disable the `uv` manager") reads
>    as an instruction to, so the wording is corrected here and in that plan.
>
> The pass also established, by direct query, that **the Mend Renovate app has never been
> enabled on this repo** and that **`main` carries no branch protection and no rulesets** —
> both of which change the sequencing (see "Operator preconditions").

## Problem

`python-kickstarter` pins dependencies across many heterogeneous surfaces, and only one of
them (`uv.lock`) is inspectable with a single command today.

| Surface | Maintainer harness | Generated project |
|---|---|---|
| uv / PEP 621 Python deps | `pyproject.toml` + `uv.lock` | `template/pyproject.toml.jinja` (+ generated `uv.lock`) |
| mise tool pins | `mise.toml` `[tools]` | `template/mise.toml.jinja` (+ `gitleaks`) |
| pre-commit hooks | `.pre-commit-config.yaml` (`rev:` SHA) *(landed since — gap #1)* | `template/.pre-commit-config.yaml.jinja` (`rev:` SHAs) |
| GitHub Actions | `.github/workflows/*.yml` (`uses:` SHAs) | `template/.github/workflows/*.jinja` |
| uvx / mise pins in run-steps | `uvx zizmor@/semgrep@/pip-audit@…` (5 sites across `justfile` + `test-template.yml`), `mise … gitleaks` *(semgrep/pip-audit/gitleaks landed since — gaps #2, #3)* | `uvx zizmor@/semgrep@/pip-audit@…`, `mise … gitleaks` |

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

A 5-angle research pass (21 sources; 105 claims; 25 spot-checked by 3-vote adversarial panels).
The aggregate confirmation rate over self-generated claims is not itself a credibility signal —
the per-claim votes on the four load-bearing bullets below do the real work. The workflow's synthesis stage degraded to a placeholder;
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
  as its cross-surface SHA-freshness mechanism (one named adopter, not a broad survey).
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

**Conclusion that drives this design:** the trust model these sources point to is Renovate
(freshness) + zizmor (Actions enforcement) — a documented pattern (Cilium for Renovate;
purpose-built tooling for zizmor), not a universally-surveyed standard. For an artifact that is "of record" and
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
  files). Deferred primarily because a bespoke guard carries real authoring/maintenance cost
  for a residual "forgot-to-wire-a-manager" gap we accept and catch with Scorecard/periodic
  audits; that no proven project relies on one is corroborating, not load-bearing (it rests on
  a single `[medium; 2-1]` claim). Its function is partly served here for free by the
  **surface-map ⟷ Renovate Detected-Dependencies cross-check** (two independent enumerations
  that should agree; disagreement is the drift signal). The residual gap is in Risks.
- **A committed SBOM / generated inventory doc.** Python-only or scan-based; false
  cross-surface confidence and drift.
- **Freshness/audit *recipes*.** `uv tree --outdated` and the advisory command are
  documented in `AGENTS.md` and run ad hoc; `just deps` stays graph-only. The template
  already ships `just audit` (gated on `enable_dependency_audit`).
- **Changing the *template's* Renovate `uv` handling.** The maintainer config (added here)
  disables the `uv` *tool* to avoid desyncing its own multi-site `uv` pins (`mise.toml` + the
  `setup-uv` inputs), which no maintainer-side test guards; the *template's* shipped config has
  the same multi-site `uv` pin (plus the `uv_build` floor) but its *rendered* pins **are**
  checked, by `test_generation.py:836-839`. Reconciling the template's Renovate-vs-uv-pins is a
  known follow-up, out of scope here (this spec adds no new downstream drift — it only adds a
  maintainer-side config). **Amended:** the template's `"pre-commit": { "enabled": true }` is a
  *separate* question that this spec's findings now put in scope for a decision — see ⑧.
- **OpenSSF Scorecard / pinact workflows.** zizmor covers Actions pin-trust; Scorecard is a
  possible future layer.
- **Adding `deps`/`deps-template` to a gate.** They are standalone, on-demand inspection — not
  blocking gates. *(Amended: this bullet originally read "a maintainer `just ci` aggregate — the
  repo has none." A `just ci` aggregate landed with gap #5; the non-goal is now specifically
  that `deps`/`deps-template` stay **off** it, matching the template, which ships no `deps`
  gate either.)*

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
  configured `--persona=regular`. **Caveat (verify in implementation):** the repo's NEVER
  rule ("don't bump a SHA without updating its exact-tag comment") maps to zizmor's
  `ref-version-mismatch` audit (added in zizmor 1.14.0), but whether it fires under
  `--persona=regular` (vs a higher persona) is unverified — so the surface-map states zizmor
  enforces *pinning* (always true via `unpinned-uses`) and claims comment-drift enforcement only
  once that persona/audit mapping is confirmed.

### Maintainer harness deliverables

**① `renovate.json` (NEW), scoped to avoid the `zizmor` parity desync and the multi-site `uv`
desync.**

**No `customManager` for `uvx <tool>@<ver>` pins.** The maintainer has **five** such pins
across three tools — `justfile:60` (`semgrep`), `justfile:70` (`pip-audit`),
`test-template.yml:54` (`zizmor`), `:106` (`pip-audit`), `:108` (`semgrep`). Only `zizmor` is
parity-locked: `test_generation.py:834` asserts the maintainer's `uvx zizmor@…` pin equals the
rendered `scan.yml` pin, so a Renovate bump of it fails the `test` matrix **loudly**. The other
two are worse, not better — `test_generation.py:825` compares two *rendered* files (the
maintainer's `justfile`/`test-template.yml` are never read) and `pip-audit` is deliberately
excluded from the drift test entirely (`:831-832`, because `scan.yml` pins an exact version
while the template's `pyproject` floors `>=X.Y`). The template layer is invisible to every
Renovate manager (every file under `template/` ends in `.jinja`), so a `semgrep` or `pip-audit`
PR would bump the maintainer sites while `template/justfile.jinja` and the template `scan.yml`
stay behind — **all gates green**, downstreams shipping a stale pin indefinitely. That is
exactly the drift `AGENTS.md`'s "bump every literal site by hand, against the template"
obligation exists to prevent. A markdown-embedded pin is untrackable regardless (see ④).

**Disable the `uv` *tool* — via `matchPackageNames`, not `matchDepNames`.** This is not to keep
a parity *test* green: `test_generation.py:836-839` reads the *rendered* project, not the
maintainer's own files, so a maintainer `uv` bump cannot touch it. The real reason is that the
maintainer's `uv` is genuinely multi-site — `mise.toml:3` plus all five `setup-uv version:`
inputs in `test-template.yml` (`:31`, `:49`, `:65`, `:81`, `:101`) — with **no** maintainer-side
test asserting they agree. Renovate sees both surfaces, but under *different depNames*: the
`mise` manager extracts depName `uv`, while the `github-actions` manager natively extracts
`astral-sh/setup-uv`'s `version:` input as depName `astral-sh/uv`. They share the packageName
`astral-sh/uv`. **`matchDepNames: ["uv"]` therefore matches only the `mise.toml` side** and
would leave the five workflow inputs free to bump — reproducing the desync in the opposite
direction. `matchPackageNames: ["astral-sh/uv"]` matches both, and does not touch the action's
own digest pin (packageName `astral-sh/setup-uv`).

**Naming discipline:** there is no Renovate manager called `uv`. `pep621` is the manager that
reads `pyproject.toml` + `uv.lock` (and it is the one that must stay **enabled**). A top-level
`"uv": {…}` key is an invalid configuration option, which aborts the repository run and opens an
"Action Required" issue — a config that looks like it closes this gap while producing zero PRs
on every surface.

**Other mise pins.** `python` and `just` are single-site in `mise.toml` and bump freely
(Renovate's `mise` manager tracks both) — though a `python` bump to 3.14 would desync from the
CI matrix (`test-template.yml:21`) and `copier.yml`'s `python_version` choice list, neither of
which any manager reads. `copier` is pinned in `mise.toml` (exact, uncapped) **and** declared as
a `uv` dev dep (`>=9.6,<10`) — the two agree today and both bump within 9.x, but a `copier` 10.x
release would push the `mise.toml` pin past the dev-dep cap, with no maintainer test asserting
they stay in sync (a known multi-site gap, like `uv`). `gitleaks` is single-site in `mise.toml`
for *execution* (`justfile` and CI both resolve from it, so local and CI cannot diverge) but its
version literal is repeated in `AGENTS.md` prose, which a Renovate bump leaves stale.

**The `pre-commit` manager stays off** — but **not** for the reason originally given here. The
harness *does* now have a `.pre-commit-config.yaml` (gap #1 landed), so "the harness has no
pre-commit config" is obsolete. The current reasons are: (a) its one non-`local` entry is
pinned to a bare 40-hex SHA, a form Renovate handles badly — a static trace of the manager
indicates the SHA is semver-coerced rather than skipped, so Renovate would propose *replacing*
it with a tag, unpinning the SHA and potentially downgrading it, while the `# v6.0.0` comment
silently goes stale; and (b) `AGENTS.md` requires that `rev:` and the template's copy be bumped
**together**, and the template copy is a `.jinja` file no manager can see. *(a) is a source
trace, not an executed run — the onboarding PR (see "Operator preconditions") settles it
empirically. (b) holds regardless, and is sufficient on its own.* Note the manager is off by
default, so the actionable form is an explicit `"pre-commit": { "enabled": false }` carrying
that rationale, rather than silence.

> **Residual risk (eyes open).** Disabling the `uv` tool leaves the most drift-prone, multi-site
> pin with no freshness and no drift detection. The freshness-preserving alternative is a
> `groupName` rule keeping the `mise` and `github-actions` deps in a single PR so both move
> together — now cheaper than when this spec was first written, since Renovate's native
> `setup-uv` support means no `customManager` is needed. Deferred here for the simpler manual
> bump, but recorded as the better long-term option.

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "helpers:pinGitHubActionDigests"],
  "lockFileMaintenance": { "enabled": true, "schedule": ["before 4am on monday"] },
  "pre-commit": { "enabled": false },
  "packageRules": [
    {
      "description": "uv is pinned in mise.toml AND every setup-uv version: input in test-template.yml, with no maintainer-side test asserting they agree. Renovate sees both (mise depName 'uv'; github-actions depName 'astral-sh/uv') but would bump them in separate PRs. Match on the shared packageName so BOTH are disabled — matchDepNames: ['uv'] would silence only the mise side. Bump uv manually across all six sites instead.",
      "matchPackageNames": ["astral-sh/uv"],
      "enabled": false
    }
  ]
}
```

**`lockFileMaintenance` is the load-bearing line, not `config:recommended`.** Every dev dep in
`pyproject.toml` is a *capped* range (`copier>=9.6,<10`, `ruff>=0.15,<0.16`,
`basedpyright>=1.39,<1.40`, …), and `pep621` exports no `getRangeStrategy`, so the default
`rangeStrategy: "auto"` resolves to `replace` — which rewrites a range only when the new version
falls **outside** it. The `pep621` manager will therefore open **zero** PRs for in-range
releases, including all three of Problem ②'s motivating examples (`copier 9.15.2→9.16.0`,
`ruff 0.15.19→0.15.20`, `pydantic-core 2.46.4→2.47.0`); it fires only on the seven rare
cap-crossing events. Those three are surfaced by the weekly `lockFileMaintenance` `uv.lock`
refresh and by nothing else — if that line is ever dropped or silently fails, the config looks
correct and does nothing on the Python surface. The built-in `mise` manager catches `copier`'s
exact `mise.toml` pin and bumps `just`/`python`/`gitleaks`; `github-actions` +
`helpers:pinGitHubActionDigests` keep the workflow `uses:` pins fresh (the latter is close to a
no-op here — every `uses:` in `test-template.yml` is already SHA-pinned with a tag comment, as
`tests/policy/test_gates.py::test_actions_are_sha_pinned` enforces).

**② `justfile` — add `deps` and `deps-template`.** `deps-template` must be a shebang recipe
(the file's `set shell := [bash -eu -o pipefail -c]` runs each plain line as a separate
`bash -c`, so a `mktemp` dir would not survive), and must pass **`--vcs-ref HEAD`**: copier
defaults to the latest SemVer tag (`v0.1.0`), so a plain `copier copy .` renders the *released*
template, not the in-development one. (`template/` is unchanged since `v0.1.0`, so the
tag-render and the HEAD-render are byte-identical today — masking this; it breaks the moment a
template change lands without a new tag.) With `ref == HEAD`, copier also folds in the dirty
worktree — exactly what "inspect the in-development template" needs. Two execution hazards the
recipe defuses: it invokes `uvx copier@9.15.2` (pinned to match `mise.toml`, not `uv run`) so an incidental stale maintainer
`uv.lock`/`.venv` is never re-synced by the inspection, and it `unset`s `VIRTUAL_ENV`/`UV_PYTHON`
(exporting `UV_PYTHON_DOWNLOADS=automatic`) so the recipe's explicit `uv lock` step (below)
resolves the rendered project's own `>= 3.13` floor with a downloaded interpreter instead of
inheriting a leaked older or pinned `UV_PYTHON` / sub-3.13 `VIRTUAL_ENV` (e.g. the 3.11 matrix
interpreter) and aborting the resolve — the same interpreter-pin leak `conftest.py`'s
`without_interpreter_pins()` scrubs.

```make
# Print the uv-resolved dependency graph from the committed lock (no resolve, no network).
deps:
    uv tree --frozen

# Inspect the in-development generated project's resolved graph: render HEAD/worktree with all
# guardrail toggles on into a throwaway dir, lock it, print the tree. `uvx copier@9.15.2` (not
# `uv run`) keeps this inspection from syncing/rewriting the maintainer's own lock/venv;
# unsetting the maintainer interpreter pin lets the explicit `uv lock` below resolve the
# rendered project's own 3.13 toolchain (else it inherits a leaked older/pinned UV_PYTHON and
# aborts); `--skip-tasks` drops every copy-time `_task` — git init, the heavy `uv sync`, the
# hook install — since we only need the lock for `uv tree`. Home-based TMPDIR keeps the
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
    uvx copier@9.15.2 copy --trust --defaults --vcs-ref HEAD --skip-tasks \
        --data project_name="Deps Probe" \
        . "$dir"
    uv lock --directory "$dir"
    uv tree --frozen --directory "$dir"
```

**③ Test-harness precondition — render HEAD in the generation-test fixture.** `conftest.py`'s
`_render` fixture calls `copier.run_copy(template_root, …)` with **no `vcs_ref`**, so it too
targets the latest tag. New assertions for `deps`/the surface-map would render `v0.1.0`
(which predates them) and **fail** once work lands post-tag. Fix: pass `vcs_ref="HEAD"` in
the `_render` fixture. This is safe today (`template/` is untouched since `v0.1.0`, so the tag-render and the HEAD-render are identical **on a clean tree**; with a dirty
worktree copier `git add -A` + wip-commits the changes into a temporary ref, so the render
reflects HEAD+worktree and emits a `DirtyLocalWarning`) and is a general
correctness fix — it lets generation tests validate the in-development template (and the
dirty worktree during TDD), not the last release. The roundtrip tests keep their explicit
`vcs_ref="v0.1.0"` (they deliberately test the release→update path). *Flagged for reviewer
attention: this touches the shared fixture, beyond "dependency visibility," but is a
precondition for criterion 5. (If `filterwarnings=error` is ever added to the suite, the
per-render `DirtyLocalWarning` must be explicitly ignored.)*

**④ `AGENTS.md` — new `## Inspect the dependency graph` section** (after the lint/format
block). The maintainer map is unconditional (no toggles in this repo):

> The inventory of record is this map + `just deps`. Renovate (`renovate.json`) keeps every
> surface fresh and its Dependency Dashboard `## Detected Dependencies` section is an
> independent cross-check.
>
> | Surface | Pinned in | Read it with |
> |---|---|---|
> | uv / Python deps | `pyproject.toml`, `uv.lock` | `just deps` (`uv tree --frozen`); freshness `uv tree --outdated`; advisories — see below |
> | mise tools | `mise.toml` `[tools]` | read the file *(Renovate `mise` manager tracks `python`/`just`/`copier`/`gitleaks`; `uv` is bump-manually)* |
> | pre-commit hooks | `.pre-commit-config.yaml` (`rev:` SHA + tag comment) | read the file *(Renovate's `pre-commit` manager is **disabled** — see ①; bump the `rev:` and the template's copy together, by hand)* |
> | GitHub Actions | `.github/workflows/*.yml` `uses:` (SHA + tag comment) | `grep -rn 'uses:' .github/workflows`; **trust:** the `zizmor` job enforces SHA pinning, and `tests/policy/test_gates.py` pins the `@<sha> # v<ver>` form |
> | uvx tool pins | run-steps (`uvx <tool>@<ver>`) — 5 sites across `justfile` **and** `.github/workflows` | `grep -rn 'uvx .*@' justfile .github/workflows` *(no Renovate manager tracks these by design; the `zizmor` pin is parity-locked to the template by a test, `semgrep`/`pip-audit` are not — bump all of them by hand, against the template)* |
> | generated project's graph | rendered template | `just deps-template` |
>
> Advisories: `just audit` (`pip-audit` over the full locked graph — the harness's deps are all
> dev, so **no** `--no-dev`; see the "Dependency audit" section for why restoring it would make
> the gate pass vacuously).

**⑤ `CHANGELOG.md` — `[Unreleased] / ### Added`** (additive → next minor): only the
**template-side** additions downstreams receive — the `deps` recipe and the `## Dependencies`
surface-map. The maintainer-only changes (`deps-template`, the maintainer `renovate.json`, the
`_render` fixture pin) stay out of the downstream changelog by deliberate scope (see Migration).

### Template (shipped) deliverables

**⑥ `template/justfile.jinja` — add an unconditional `deps:` (`uv tree --frozen`)** beside
`lint`/`typecheck`.

**⑦ `template/AGENTS.md.jinja` — extend the existing `## Dependencies` section** with the
surface-map. **Correct toggle gating** (verified against the actual toggles):

| Row / note | Gate |
|---|---|
| uv/Python deps row, `just deps` | unconditional |
| `uv_build` build-system floor (`[build-system].requires`) named as a uv-pin site **not** covered by the rendered-pin drift test (`test_generation.py:836-839`) | `project_type == "library"` (applications render `[tool.uv] package = false`, no floor) |
| mise tools row (`[tools]` always ships) | unconditional |
| pre-commit `rev:` row (`.pre-commit-config.yaml` ships unconditionally — there is **no** `enable_precommit` toggle) | unconditional |
| GitHub Actions row | unconditional; **zizmor trust note** → `enable_sha_pin_policy` |
| uvx scanner-pins row + gitleaks-as-scanner note | `enable_scanners` |
| advisories note (`just audit` / pip-audit) | `enable_dependency_audit` |
| Renovate lead sentence + every "Renovate … tracks it" parenthetical (the `renovate.json` ships only under `{% if enable_renovate %}`) | `enable_renovate`; **fallback** lead when off: point to `just deps` + this in-repo map |

**⑧ Verify `template/{% if enable_renovate %}renovate.json{% endif %}.jinja`** (the
conditional-name idiom — there is no literal `template/renovate.json.jinja`). It already
carries `config:recommended`, `helpers:pinGitHubActionDigests`, `"pre-commit": {enabled:true}`,
and a `customManager` matching `uvx (semgrep|zizmor|pip-audit)@…`; `gitleaks` **is** covered by
the mise manager (`mise registry` resolves it to `aqua:gitleaks/gitleaks`, and `aqua` is a
Renovate-supported backend).

**Amended — "no change expected" no longer holds; one decision is now required.** The template
ships `"pre-commit": { "enabled": true }` (pinned by `tests/test_generation.py:483`) *alongside*
bare-SHA `rev:` values in `template/.pre-commit-config.yaml.jinja`. That is the same
SHA-plus-enabled-manager combination the maintainer config deliberately avoids in ①, and it is
the higher-blast-radius artifact because it ships to every downstream. Decide explicitly, in the
same body of work, between:
- flipping it to `false` (matching the maintainer config), or
- converting the template's `rev:` lines to the `# frozen: vX.Y.Z` form that
  `pre-commit autoupdate --freeze` writes, which is the one shape Renovate updates while
  *keeping* the SHA pinned.

Either choice must update the `:483` assertion in the same commit. Because this is a `template/`
change it is downstream-visible and must ride a release tag (see Migration). Resolving it is
cheap to defer until the onboarding PR confirms the underlying Renovate behaviour empirically —
but it should not be dropped.

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
- **`project_type`:** the `uv_build` build-system-floor mention present in a **library** render
  and **absent** in an **application** render (which has no `[build-system]` block), so ⑦'s
  library-gating of that mention is guarded.
- **`enable_sha_pin_policy`:** the GitHub-Actions row's zizmor trust-note — anchored on the
  stable `unpinned-uses`/SHA-pinning phrase, **not** the conditional comment-drift sentence —
  present when on, **absent when off** (render the off-case with `enable_sha_pin_policy=False`
  and another toggle on, mirroring the existing pip-audit both-ways test) — without this the
  zizmor trust-note is unguarded and criterion 5 is unmet.
- **`enable_renovate`:** the Renovate lead/`Detected Dependencies` phrasing present when on;
  when off, assert the substring `Renovate` is **wholly absent** from the rendered
  `## Dependencies` section (catching any ungated per-row "Renovate … tracks it" parenthetical,
  not just the lead), replaced by the `just deps` fallback.
- **runtime:** the rendered project's `just deps` exits clean (extends the existing
  install-and-run harness; relies on the `vcs_ref="HEAD"` fixture fix from ③).

## Operator preconditions

- **Renovate freshness requires enabling the app — make it an explicit step.** The inventory of
  record is in-repo (the surface-map + `just deps`), so nothing is hollow if the Renovate app is
  absent — only the *freshness PRs and the auto-detected cross-check* lapse. But those are
  exactly what Goal 1 promises, and **committing `renovate.json` produces zero PRs, zero
  dashboard, and zero cross-check on its own**: the Mend Renovate GitHub App (or a self-hosted
  runner) must be enabled on `maybebyte/python-kickstarter`. Enabling it is a required step to
  close Goal 1 (tracked in the Sequence), not just a recommendation.
- **Confirmed 2026-08-04: the app has never been enabled.** Established by the absence of every
  artifact it would create — zero `renovate`-authored PRs (`gh pr list --state all`: 10 PRs, all
  human-authored), zero issues *ever* opened on the repo (so no Dependency Dashboard, which
  `config:recommended` would create via `:dependencyDashboard`), and no `renovate/*` remote
  branch. Direct interrogation is blocked by token scope (`/user/installations` → 403), so this
  is an argument from absence — but a conclusive one for a public repo with 75 commits since
  creation. Issues are enabled on the repo, so this is not a disabled-issues false negative.
- **Install the app BEFORE committing `renovate.json`, not after.** With no config on the
  default branch, Renovate raises a *reversible* onboarding PR on `renovate/configure` and makes
  no other change until it is merged; closing it undoes everything. That PR's body carries
  Renovate's own auto-detected dependency inventory — which manager sees which file, and what
  depName/packageName each pin resolves to. That is the empirical ground truth this design has
  so far been reconstructing by reading Renovate's source, and it is precisely the "independent
  auto-detected cross-check" the Trust model already assigns to Renovate. Committing the config
  first skips onboarding entirely and throws that free dry run away. Write the scoped config
  *into* the onboarding branch (the PR updates in place) and merge it.
- **`main` has no branch protection and no rulesets** (confirmed 2026-08-04:
  `/branches/main/protection` → 404, `/rulesets` → `[]`). This matters because the safety
  argument for the whole `uvx`/parity design is "the test would go red" — with nothing blocking
  merge, red is advisory, and a Renovate PR can be merged past a failing gate. Adding required
  status checks on `main` is the cheapest single change that makes the rest of this design
  enforceable rather than advisory. Operator step; not something the implementation can do.

## Migration / release impact

- The template change is **purely additive** (a new recipe + an extended doc section);
  downstreams receive it on `copier update` with no conflicts and **no `_migrations` entry**.
- Lands under `[Unreleased]`; additive → next **minor** (0.1.0 is cut). The maintainer
  `renovate.json`, the recipes, and the `_render` fixture change are maintainer-only.

## Verification strategy

| piece | how it's verified |
|---|---|
| maintainer `renovate.json` | `npx --yes --package renovate@<pin> -- renovate-config-validator` passes (it auto-detects `renovate.json`; there is **no** standalone `renovate-config-validator` npm package — it ships inside `renovate`). Pin the version rather than `renovate@latest`, and note it needs a Node runtime — a dev-only tool in no tracked surface (no `package.json`; `mise.toml` pins no node). This validation is **manual/one-time, not a CI gate** — like the template's own shipped `renovate.json`, it is unguarded in CI, so a later invalid edit would not fail a build (accepted tradeoff; a shared validator job could cover both) |
| no parity desync | `test_tool_version_pins_have_no_drift` (`test_generation.py:800-839`) is unaffected — its `semgrep` and `uv` assertions read the *rendered* project, and its one maintainer-facing assertion (`:834`, `zizmor`) stays single-version because the config omits a `customManager`. The multi-site `uv` pins stay in sync because the config disables packageName `astral-sh/uv` (**not** depName `uv`, which would cover only the `mise.toml` site). **Caveat:** nothing guards `semgrep` or `pip-audit` parity — see the new maintainer↔template parity risk below |
| `just deps` (both layers) | prints `uv tree --frozen` output; rendered-project run asserted in `test_generation.py` |
| `just deps-template` | renders HEAD/worktree all-guardrails-on with `--skip-tasks` (every copy-time `_task` — uv sync, hook install — skipped), locks, prints the tree, cleans up; exit 0 |
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
  Note this is now *recurring* rather than occasional: `lockFileMaintenance` runs weekly and
  moves `ruff` within `>=0.15,<0.16`, so the mechanism fires on a schedule, against a 6-cell
  OS×Python matrix, with the non-hermetic `just audit` in the same run.
- **Renovate can only ever bump ONE of the two layers.** Every file under `template/` ends in
  `.jinja` (except `.editorconfig`, `LICENSE-APACHE.txt`, and `py.typed`), so **no** Renovate
  manager can match the template layer — not `github-actions` (needs `\.ya?ml$`), not `mise`
  (needs a `.toml` terminal), not `pre-commit`. Every Renovate PR that touches a pin duplicated
  across the two layers will therefore desync them, every time. Today the *only* cross-layer
  guard is the `zizmor` assertion at `test_generation.py:834`; the four Action SHAs, `semgrep`,
  `pip-audit`, `gitleaks`, and the `pre-commit` `rev:` are all unguarded, and `AGENTS.md`'s
  hand-sync obligations are prose that cannot fail a build. **This makes a maintainer pin-parity
  policy test a precondition for landing `renovate.json`, not a follow-up** — the first Renovate
  PR merges before anyone would otherwise write it. Extend `tests/policy/` with assertions that
  compare literals *without* hardcoding versions, the pattern
  `test_tool_version_pins_have_no_drift` already uses downstream. This widens the policy suite's
  declared scope (`AGENTS.md` currently says it pins config literals, not recipe bodies), so say
  so in the same commit.
- **Prose version literals are collateral.** `AGENTS.md` carries version literals for `gitleaks`,
  `semgrep`, `pip-audit`, and — the one a *weekly* automated PR will invalidate — `ruff`
  ("locked 0.15.19", derived from `uv.lock`). Nothing tests any of them. Landing Renovate also
  falsifies `AGENTS.md`'s three standing "**the maintainer has no Renovate**, so the pins are
  static" claims, which must be swept in the same commit that adds `renovate.json`.
- **Two Renovate configs are intentionally different, not parity-bound.** The maintainer
  config omits the `customManager` and `pre-commit` manager and disables `uv` (all for the
  reasons above); the template's keeps them. There is no parity invariant to enforce — the
  difference is documented here, so the earlier "unenforced parity" concern is moot.
- **`deps-template` render cost.** With `--skip-tasks` the recipe resolves only the lock
  (`uv lock`), skipping copier's copy-time `uv sync` and its bundled-Node download; it still
  fetches and resolves the dependency graph, so it is a several-seconds convenience, not a gate.
- **`_render` fixture change has blast radius.** Pinning the fixture to `vcs_ref="HEAD"`
  changes every generation test's render target. Safe now (`template/` unchanged since `v0.1.0` → identical render **on a clean tree**) and
  correct (validate the in-development template), but it is a harness-wide behavioral change to
  call out at review — and every dirty-tree render now emits copier's `DirtyLocalWarning` and
  pays a wip-commit cost.
- **The evidence basis is a single, partially-degraded run.** The design rests on one
  deep-research pass (`wf_812c2942-714`) whose synthesis stage degraded to a placeholder, with
  no replication. The judgment that an in-repo, test-asserted record beats an optional dashboard
  survives even if the research is wrong; the "documented practice" framing and the
  completeness-guard non-goal are what would weaken — treat those as the softest claims here.

## Sequence

**Amended 2026-08-04 — the original order put `renovate.json` first and the app second. That is
backwards:** it forfeits the onboarding dry run, and it lets the first Renovate PR land before
any cross-layer parity guard exists. `_render` fixture `vcs_ref="HEAD"` has since landed (PR #4)
and drops out of the sequence.

1. **Cut a release tag.** `main` is 75 commits past `v0.1.0`, which already violates the Release
   rule in `AGENTS.md`. Doing it now gives a clean pre-Renovate baseline (so "did a dep bump
   break the template contract" stays bisectable against a release), keeps bot-authored commits
   out of the tree being tagged, and unblocks the ⑧ template-side fix, which is invisible to
   downstreams until a tag exists.
2. **Maintainer pin-parity policy test** — before any Renovate config merges (see Risks).
3. **Operator: enable the Mend Renovate app** with no config committed; read the onboarding PR's
   detected-dependency inventory and reconcile it against this spec's Problem table. This is the
   empirical check that settles the `pre-commit`-manager and `rangeStrategy` questions.
4. **Operator: add branch protection / required status checks on `main`**, so the parity test
   from step 2 actually blocks a merge.
5. **Write the scoped `renovate.json` into the onboarding branch and merge it**, sweeping
   `AGENTS.md`'s "no Renovate" claims in the same commit.
6. Then the inventory deliverables, unchanged in order: `just deps` + `deps-template` recipes →
   maintainer `AGENTS.md` surface-map → `CHANGELOG` → template `justfile.jinja` `deps` →
   template `AGENTS.md.jinja` surface-map (toggle-correct) → `test_generation.py` present/absent
   assertions → resolve the ⑧ template Renovate `pre-commit` decision.

The detailed, commit-by-commit plan is produced next by `writing-plans`.
