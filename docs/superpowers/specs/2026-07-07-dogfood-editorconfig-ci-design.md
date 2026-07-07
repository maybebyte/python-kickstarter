# Dogfood editorconfig + aggregate ci — design (2026-07-07)

## Goal

Close two Phase-1 dogfooding gaps from `docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md` §7 item #4 in one bundle, both instantiating template layers the maintainer already ships but does not run on itself:

- **Gap #7 — editorconfig.** `template/.editorconfig` is shipped verbatim and unconditionally into every downstream; the maintainer repo carries no root `.editorconfig`, yet is full of files it governs (`tests/*.py`, 2-space YAML/TOML in `pyproject`/`mise`/`copier`/workflows). The template enforces it **passively** (no editorconfig-checker in its pre-commit/justfile/CI), so full parity is met by dropping the verbatim file at root — values already match repo conventions, zero conflict.
- **Gap #3 — aggregate `just ci`.** `template/justfile.jinja` ships `ci: fmt-check lint typecheck test{…conditional fuzz/policy/audit}` + `@echo "ci: all gates passed"` and `verify: ci`. Every gate the aggregate would chain already runs here as a standalone recipe and a PR-blocking CI job; only the unified local entry point is absent.

Governing principle (as at every prior gap): **mirror the template; diverge only where the maintainer surface forces it, and document each forced divergence in AGENTS.md.**

### Empirical anchors (verified against the tree, not roadmap prose)

- `template/justfile.jinja:7` **chains `audit` into `ci`** via `{% if enable_dependency_audit %} audit{% endif %}` — and that toggle is on/dogfooded. So the faithful maintainer mirror **includes `audit`**: `ci: fmt-check lint typecheck test audit`. (An earlier draft dropped `audit` on a "non-hermetic forces divergence" premise; that premise is factually wrong — it is the same pip-audit the template chains anyway — and was reversed in review.)
- `template/.editorconfig` glob is `[*.{yml,yaml,json}]` — **not** `{…,toml}` (roadmap §115 misstates this). `tests/test_generation.py:96` asserts `"toml" not in editorconfig`, so a verbatim `cp` is both correct and keeps the downstream assertion coherent.
- The template ships **no** `check:` recipe; the fast inner loop is the ad-hoc `just fmt-check lint typecheck`.

## Decisions

- **D1 — `audit` is a member of `ci`.** Mirror the template exactly: `ci: fmt-check lint typecheck test audit`. Dropping it would be an unforced, taste-based divergence the governing principle disqualifies; `audit` is itself a PR-blocking check here (the `scan` job's `pip-audit` step), so the local aggregate must reproduce it.
- **D2 — `test` (the full generation matrix) stays in `ci`.** It is the maintainer's analog of the template's `test`; omitting it defeats the gap. Because it is heavy and fills the default 4G tmpfs `/tmp`, document the roomy-`TMPDIR` requirement (recipe comment + AGENTS section + verification).
- **D3 — no `check:` fast split.** The template ships none; a named recipe would be an unforced divergence with zero new capability. Document the one-liner `just fmt-check lint typecheck` instead.
- **D4 — `verify: ci` added verbatim.** Free exact parity with the template's bare alias.
- **D5 — candidate F (point CI jobs at `just` recipes) is deferred.** Not folded into this bundle. The real cost is restructuring the `scan` job — pip-audit + semgrep + gitleaks are three steps that do not map onto the `audit`+`scan` recipe split (different tool subsets + `mise` handling), so F is a genuine restructure on the zizmor-gated workflow, not a one-line swap. Acknowledged consequence: shipping `ci` now creates a second encoding of the gate set (recipe vs the four parallel CI jobs) that can drift; the follow-up F PR must reconcile it.
- **D6 — bundle editorconfig + ci in one PR.** Roadmap §176 bundles them; both are trivial and both touch AGENTS.md. (editorconfig alone has no dependency on anything and could ship standalone, but bundling stays coherent.)
- **D7 — scanners stay off `ci` (CI-only), unchanged.** Both template and maintainer keep `scan` out of `ci`; the `scan` recipe/prose "off `ci`" wording remains true and is left untouched.
- **D8 — `ci` does not chain `precommit`.** Local-only, no CI job — matches the template.

## Wiring

### `.editorconfig` (root, gap #7)

Byte-for-byte `cp template/.editorconfig .editorconfig` (11 lines, trailing newline, glob `[*.{yml,yaml,json}]`). No generation-test change: this is a maintainer-root file, not a `template/` file, so the "NEVER add a `template/` file without an assertion" rule is inapplicable; `test_generation.py:92-96` continues to assert the *rendered downstream* file.

### `justfile` (gap #3)

Insert immediately after the `default:` recipe, mirroring the template's ci-first ordering:

```just
# The complete local gate — every PR-blocking check, reproducible locally.
# Mirrors template/justfile.jinja's `ci` (audit is a member — the template chains it,
# and audit is itself a PR-blocking check here via the CI `scan` job's pip-audit step).
# `test` is the full generation matrix: give it a roomy TMPDIR (the default 4G tmpfs
# /tmp can overflow) — see "Run every gate" in AGENTS.md. Scanners stay CI-only (off `ci`).
ci: fmt-check lint typecheck test audit
    @echo "ci: all gates passed"

verify: ci
```

`@echo "ci: all gates passed"` and `verify: ci` are exact template strings. The operator's absolute TMPDIR is **not** hardcoded in the committed comment.

### `justfile` — live-site consistency edits (introducing `ci` falsifies them)

The `audit` recipe's comment block is rewritten in two places, because `audit` is now a `ci` member (no longer "out-of-band"):

- header: `# Out-of-band dependency vulnerability audit: pip-audit over the FULL locked graph.` → `# Dependency vulnerability audit: pip-audit over the FULL locked graph.`
- CI-enforcement line: `# Enforced in CI by the `scan` job, not a `ci` recipe (there is none).` → `# Chained into `just ci` (mirrors the template) and independently enforced in CI by the `scan` job's pip-audit step.`

The `scan` recipe's comment (`# Out-of-band secret + SAST scan … not `ci`.`) is **left unchanged** — scan genuinely stays off `ci`, so its wording remains true. This is the crux of the mirror decision: `audit` follows the template onto `ci` (and sheds "out-of-band"); `scan` does not.

### `AGENTS.md` — new section + two live-site edits

New `## Run every gate (`just ci`)` section inserted after the intro line (before `## Run the tests`), documenting: the recipe shape (`fmt-check lint typecheck test audit` + echo; `verify` alias); the roomy-`TMPDIR` requirement and the `just fmt-check lint typecheck` fast subset; that `audit` is chained in (mirrors the template) while scanners stay CI-only; the maintainer-vs-downstream `just ci` disambiguation; a **forward-sync note** (when gap #4 policy / #9 fuzz land, both the recipe and this section must gain `policy`/`fuzz` to keep mirroring the template's conditional `ci`); the CI note (maintainer CI keeps parallel per-gate jobs + matrix and spells `uv run …` inline, does not run `just ci`; candidate F deferred); and the forced-divergences paragraph.

The Dependency-audit section's stale `ci`-related wording is rewritten (all falsified by the new `ci` recipe, since `audit` is now a `ci` member):
- fence comment `just audit   # out-of-band dependency vulnerability audit…` → `just audit   # dependency vulnerability audit … (also a `just ci` member)`
- `AGENTS.md:61` "It is out-of-band (chained into no recipe), but CI enforces it: the `pip-audit` step…" → "It is chained into `just ci` (the local aggregate) and independently enforced in CI: the `pip-audit` step…"
- `AGENTS.md:63` "…and it is out-of-band, not a `just ci` dependency (the template makes `audit` gating — the maintainer has no `ci` recipe)." → "…. Like the template, `audit` is chained into `just ci` (see "Run every gate"); it is additionally enforced in CI as the `pip-audit` step in the `scan` job."

The `scan` section's "out-of-band" wording (fence + prose) is **unchanged** — scan stays off `ci`.

### CI / generation-test / dep / mise / CHANGELOG

**None.** No `test-template.yml` edit (F deferred). No `pyproject.toml`/`mise.toml`/`tests/` change. No CHANGELOG entry — the existing `[Unreleased]` `.editorconfig`/`ci` lines describe the **template product** (rendered downstream, consumed via `copier update`); this PR touches only the maintainer's own dogfood surface, matching gaps #1/#2/#5.

## Documented divergences (mirror-except-where-surface-differs)

- **`ci` gate list: no divergence** — the maintainer mirrors `ci: fmt-check lint typecheck test audit` (audit included because `enable_dependency_audit` is on); `verify: ci` and the echo line are exact.
- **Structural divergence (not in `ci` itself):** the maintainer's CI never runs `just ci`; it keeps parallel per-gate jobs (`test`/`typecheck`/`lint`/`scan`) and an OS×Python matrix, each spelling `uv run …` inline, whereas the template's downstream `ci.yml` runs the single command `just ci`. So `just ci` here is the local reproduction of the PR gate, not the CI entry point.
- **No `check:` split** — the template ships none; the fast subset is the ad-hoc `just fmt-check lint typecheck`.
- **Candidate F deferred** — see D5.
- (The `audit` recipe's dropped `--no-dev` is a separate, already-documented divergence in the Dependency-audit section, not a `ci`-list divergence.)

## Acceptance

- `TMPDIR=<roomy> just ci` runs fmt-check + lint + typecheck + test + audit and ends with `ci: all gates passed`.
- `just --show verify` shows `verify: ci` (thin alias; not re-run).
- `just precommit` clean (the new root `.editorconfig` is not `^template/`-excluded, so it must end in `\n`; the verbatim copy does).
- Root `.editorconfig` byte-identical to `template/.editorconfig`.
- Every falsified live site updated — the `audit` recipe's header + CI-enforcement comments, and the Dependency-audit section's fence + two prose clauses; `grep -ni 'out-of-band' justfile AGENTS.md` returns **only** `scan`/generic references, and `grep -nF -e 'there is none' -e 'no `ci` recipe' justfile AGENTS.md` returns nothing.
- Clean tree; `requirements-audit.txt` gone (rm'd by the audit step on success).
- CI green on the PR (no workflow change; zizmor N/A).

## Out of scope / tracked follow-up

- **Candidate F** (CI jobs call `just` recipes) — deferred to a follow-up that must reconcile the `scan`-job restructure with the new recipe encoding (D5).
- **`check:` fast split** — deliberately not added (D3).
- **~8 stale "no `ci` recipe" mentions in dated `docs/superpowers/` files** — left frozen as historical snapshots, consistent with the pin-sync convention (which enumerates only recipe + CI job + "the prose above", never design docs). Not swept.
- Later Phase-1 items: policy-tests (#4, closes #8) → renovate (#6) → property-tests (#9). The policy/fuzz layers will trip the AGENTS forward-sync note.

## Explicit no-touch (guard rails)

- No file added under `template/` (so no generation-test obligation).
- No `test-template.yml`, `pyproject.toml`, `mise.toml`, `uv.lock`, `tests/`, or CHANGELOG change.
- No `scan`/`audit` recipe body change; no scanner "off `ci`" wording change (still true).
- No inline `# noqa`; no Action SHA bump.

## Files touched (maintainer root only)

- `.editorconfig` (new, verbatim)
- `justfile` (add `ci`/`verify`; edit the audit-recipe comment)
- `AGENTS.md` (new "Run every gate" section; rewrite two audit-section clauses)
- `docs/superpowers/specs/2026-07-07-dogfood-editorconfig-ci-design.md` + `docs/superpowers/plans/2026-07-07-dogfood-editorconfig-ci.md` (this pair)

## Endorsed decisions (verified in adversarial review — do not reopen)

- `audit` **is** in `ci` (D1) — reversal of the earlier draft; template L7 chains it.
- `.editorconfig` is a verbatim `cp` with glob `{yml,yaml,json}` (no `toml`); roadmap §115 is wrong.
- No generation-test change (root file, not `template/`).
- Only the **two live sites** are swept; dated docs stay frozen.
- Candidate F and the `check:` split are deliberate scope reductions, not omissions.
