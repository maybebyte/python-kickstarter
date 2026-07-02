# Dogfood secret + SAST scanners (gitleaks + semgrep) — design (2026-07-01)

## Goal

Run the same secret-scanning + SAST gate the template ships (`enable_scanners`)
on the maintainer repo itself, adapted to the maintainer's actual surface (one
workflow with per-tool jobs; `tests/` the only Python; no `src/`; `template/` is
Jinja), green from the first commit. This closes gap #2 of the dogfooding-gap
audit (`docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md`) — the one
substantive *security* gap: a secret committed (even then deleted) to the
maintainer repo is currently uncaught by the very tool it ships.

This design was produced from a multi-agent audit and adversarially reviewed,
then corrected during execution by an empirical finding (below). Both scanners
run green today: gitleaks scanned all 161 commits with no leaks, and semgrep
exits clean.

**Empirical finding — semgrep is currently inert on the maintainer.** semgrep's
built-in `.semgrepignore` excludes `tests/` (and `test/`), and there is no
`src/`, so semgrep scans **0 files** on the maintainer today (verified:
`Targets scanned: 0`). This is faithful to the template, which runs the identical
command against downstream **product code** (`src/PKG`) and ignores its `tests/`
too — the maintainer simply has no product Python. semgrep is therefore kept as a
byte-parity mirror and **forward guard**: it validates the shipped config on the
real repo and fires the moment any non-test Python is added at root. gitleaks is
the substantive gate here. (Alternative considered: drop semgrep as
not-applicable, like mutmut/coverage — see Out of scope.)

**Scope:** gitleaks + semgrep only. pip-audit (gap #5) shares the template's
`scan.yml` but is a separate gap and a separate PR; it will add one step to the
`scan` job introduced here (see Out of scope).

## Decisions

Nine forks were resolved; all but two settle by "mirror, don't diverge." The two
open ones (pip-audit scope, pin-drift governance) were resolved with the
recommended options and remain revisitable at spec review.

1. **gitleaks command: `gitleaks git . --redact --exit-code 1` (history), not
   `gitleaks dir`.** The gap-audit plan doc claimed the template's local recipe
   uses `gitleaks dir`; that is **stale** — `template/justfile.jinja:50` ships
   `gitleaks git .`, and `test_generation.py` asserts `gitleaks git .` present /
   `gitleaks dir` absent. History scan catches secrets committed then deleted;
   it forces `fetch-depth: 0` on the CI job.
2. **CI shape: a new `scan` *job* inside the existing `test-template.yml`, not a
   separate `scan.yml`.** The maintainer runs one workflow with per-tool jobs
   (test / zizmor / typecheck / lint); the template's consolidation into
   `scan.yml` is a downstream-only shape. A sibling job keeps the existing zizmor
   job (which scans `.`) auditing the new job.
3. **zizmor stays its own job — not merged into `scan`.** The template folds
   zizmor into `scan.yml` gated on `enable_sha_pin_policy`; the maintainer
   already dogfoods zizmor standalone, so it must not be duplicated.
4. **Run mechanisms mirror the template:** gitleaks pinned once in `mise.toml`
   and run in CI via `jdx/mise-action` + `mise exec -- gitleaks`; semgrep via
   `uvx semgrep@1.167.0` (no pyproject dep — the "uvx-run tools skip the dep"
   convention, matching zizmor).
5. **semgrep target: `.`** (verbatim mirror). The rule is `languages: [python]`,
   and semgrep's built-in `.semgrepignore` excludes `tests/`; with no `src/`, the
   maintainer has **0 scannable files today** (see the empirical finding in Goal).
   `.` is kept for byte-parity with the template (which scans downstream `src/`)
   and auto-covers any future non-test Python added at root. Hermetic flags
   `--config .semgrep.yml --metrics=off --error` are non-negotiable — never
   `--config auto`.
6. **`scan` stays out-of-band** — not chained into any recipe. The template's
   `ci` recipe omits scan ("scanners run in CI only"); the maintainer has no `ci`
   recipe at all, and the pre-commit dogfood likewise kept `precommit` off any
   aggregate. The CI `scan` job is the enforcer.
7. **`timeout-minutes: 15`** on the scan job — the template's budget for this
   workload (a history scan is heavier than a workflow audit), vs the
   maintainer's 10 on zizmor/typecheck/lint.
8. **Local `just scan` uses bare `gitleaks git .`** (byte-parity with
   `template/justfile.jinja:50`). Verified safe: the maintainer shell activates
   mise (`mise activate` in `config.fish`; tool install dirs on `$PATH`), so
   `gitleaks` resolves after the pin is added — no `mise exec` wrapper needed
   locally. (CI still uses `mise exec`, exactly as the template does.)
9. **No generation/policy self-test for the mirror** — the new files are at
   ROOT, not under `template/`, so NEVER-rule #1 does not fire (same reasoning
   the pre-commit dogfood used; it added none). Pin-drift governance is handled
   by an AGENTS.md manual-sync note instead (see Decisions/governance below).

**Pin-drift governance (resolved: AGENTS.md note).** The maintainer's semgrep
`1.167.0` and gitleaks `8.30.1` pins are **unguarded here**: the maintainer has
**no Renovate at all** (unlike downstream — verified: no root `renovate.json`),
and the generation drift test reads only the *rendered* downstream, never the
maintainer surfaces. Rather than add a parity test (that is really gap #4,
policy-tests — scope creep here), the new AGENTS.md section names the manual
sync obligation, mirroring the existing pre-commit "bump both `rev:` pins
together" precedent.

## The configs (repo root, verbatim from the template)

`.gitleaks.toml`:

```toml
# gitleaks config — extend the default ruleset.
[extend]
useDefault = true
```

`.semgrep.yml`:

```yaml
rules:
  - id: no-eval
    languages: [python]
    severity: ERROR
    message: Avoid eval(); it executes arbitrary code.
    pattern: eval(...)
```

Both are plain files (not `.jinja`) and **unconditional** — there is no
`{% if enable_scanners %}` guard to reproduce at root. `.gitleaks.toml` is
auto-discovered at repo root (no `--config` flag is passed to gitleaks; renaming
or moving it silently reverts to gitleaks' embedded defaults). `.semgrep.yml` is
referenced by path in both the recipe and the CI step (`--config .semgrep.yml`).

## Wiring

### `mise.toml`

Add one line under `[tools]`, byte-identical to `template/mise.toml.jinja:8`
(unconditional — this is a concrete file, not Jinja):

```toml
gitleaks = "8.30.1"
```

This is the single source of truth the CI `scan` job installs gitleaks from via
`mise exec`. **Never** hardcode `8.30.1` or a `releases/download` URL in the
workflow.

### `justfile`

Add an out-of-band `scan` recipe. The two command lines and the inner comment
are byte-identical to `template/justfile.jinja:48-50`; a maintainer-style header
comment is added above `scan:` (the maintainer justfile puts `#` comments above
its recipes — a surface convention, not substance):

```just
# Out-of-band secret + SAST scan (semgrep + gitleaks); enforced in CI by the `scan` job, not `ci`.
scan:
    uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
    # `git` (not `dir`): scan committed history like CI, catching secrets committed then deleted.
    gitleaks git . --redact --exit-code 1
```

semgrep runs via `uvx` (not `uv run`), matching the template and the existing
zizmor invocation. `scan` is **not** added to any aggregate (there is no `ci`
recipe here; if gap #3's `just ci` later lands, scanners stay out of it, like
the template).

### `.github/workflows/test-template.yml`

Append a fifth job, `scan`, modeled on the existing `zizmor` job. Placement is
positional-only (all jobs run in parallel, no `needs`); appended after `lint` to
keep the diff a pure addition:

```yaml
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          # Full history so gitleaks can catch secrets committed then deleted.
          fetch-depth: 0
          persist-credentials: false
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
        with:
          version: "0.11.23"
          enable-cache: true
      - name: semgrep
        run: uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
      # gitleaks is installed from the mise.toml pin (single source of truth);
      # install: false brings up the mise CLI only.
      - uses: jdx/mise-action@e6a8b3978addb5a52f2b4cd9d91eafa7f0ab959d # v4.2.0
        with:
          install: false
      - name: gitleaks
        run: |
          mise install gitleaks
          mise exec -- gitleaks git . --redact --exit-code 1
```

Load-bearing details, all verified against the audit + zizmor precedent:

- **`jdx/mise-action@e6a8b39… # v4.2.0`** is a *new* action for this workflow
  (which today uses only checkout / setup-uv / setup-just). It is SHA-pinned with
  its exact-tag comment per NEVER-rule #2. `checkout@9c091bb… # v7.0.0` and
  `setup-uv@fac544c… # v8.2.0` keep the SHA + comment byte-identical to every
  other job.
- **No `GH_TOKEN` env** on the scan/gitleaks steps — gitleaks needs no GitHub
  API (unlike zizmor). Do not copy zizmor's `env:` block blindly.
- **No `uv sync`** — uvx and mise are isolated, exactly like the zizmor job.
- The mise-action comment **drops the template's "kept fresh by Renovate's
  native mise manager" clause** — the maintainer has no Renovate, so that
  freshness story is template-only.
- **Do not touch the zizmor job or its `1.26.1` pin.** `test_generation.py`
  asserts the maintainer `test-template.yml` zizmor version equals the rendered
  `scan.yml` zizmor version (a set of size 1). The new `scan` job's `semgrep`
  line contains no `zizmor` token, so it is safe; keep `zizmor` mentions in this
  file to the single pinned run-line so the drift regex cannot inflate the set.

### `AGENTS.md`

Add a peer `## Scanning` H2 immediately after `## Pre-commit`. Unlike the
pre-commit section, it **can** use the "CI enforces it" refrain (the `scan` job
is a blocking gate). It documents the recipe, the configs + gitleaks mise pin,
the divergences from `scan.yml.jinja`, and the manual pin-sync obligation:

````markdown
## Scanning

```bash
just scan   # out-of-band secret + SAST scan: semgrep (no-eval) + gitleaks (full history)
```

`just scan` runs semgrep's `no-eval` rule over the tree (`.semgrep.yml`) and a
gitleaks **full-history** secret scan (`.gitleaks.toml` = default ruleset). It is
out-of-band (chained into no recipe), but CI enforces it: the `scan` job in
`.github/workflows/test-template.yml` is a blocking PR gate. gitleaks is pinned
in `mise.toml` (`gitleaks = "8.30.1"`) and installed in CI via `jdx/mise-action`
+ `mise exec`; semgrep runs via `uvx semgrep@1.167.0` (no dep, like zizmor).
semgrep scans non-test Python only — its built-in `.semgrepignore` excludes
`tests/`, and there is no `src/`, so on this repo it currently scans **0 files**
(it mirrors the shipped gate and fires if any non-test Python is added at root).
gitleaks scans the whole tree + full history regardless of language, and is the
substantive gate here. Never pass semgrep `--config auto` (it drops the pinned
rule and needs metrics on); never hardcode the gitleaks version in CI (install
via `mise exec`).

Deliberate divergences from the template's `scan.yml`
(`template/.github/workflows/…scan.yml….jinja`): the maintainer folds scanning
into the existing `test-template.yml` as a sibling
`scan` job (the template consolidates into a standalone `scan.yml`), matching the
one-workflow / per-tool layout and letting the existing zizmor job audit it;
zizmor stays its own job here rather than a step in `scan` (already dogfooded
standalone). The CI `mise-action` comment drops the template's "kept fresh by
Renovate" note — **the maintainer has no Renovate**, so the pins are static.

Because nothing here re-derives the pins (no Renovate; the generation drift test
reads only the *rendered* downstream), **bump every literal site by hand, against
the template.** gitleaks (`8.30.1`) has two maintainer sites — `mise.toml` and the
prose above — synced to `template/mise.toml.jinja` (CI installs via `mise exec`,
so there is no third gitleaks literal). semgrep (`1.167.0`) has three — the
`just scan` recipe, the `scan` job in `test-template.yml`, and the prose above —
synced to `template/justfile.jinja` and the template `scan.yml`. (Mirrors the
pre-commit "bump both `rev:` pins together" obligation.)
````

## Documented divergences (mirror-except-where-surface-differs)

- **CI shape** — a `scan` *job* in `test-template.yml`, not a standalone
  `scan.yml`. Surface: the maintainer's single-workflow / per-tool layout.
- **zizmor not merged into `scan`** — already dogfooded as its own job; the
  template only folds it into `scan.yml` downstream.
- **mise-action comment drops the Renovate-freshness clause** — the maintainer
  has no Renovate; the pin is static and manually synced (see the AGENTS.md
  note). This is the audit critic's key correction.
- **`fetch-depth: 0` is per-job** on `scan` (split-job layout) rather than the
  template's single conditional checkout; the `test` job already uses
  `fetch-depth: 0` while zizmor/typecheck/lint stay shallow.
- **Unconditional root files** — no `{% if enable_scanners %}` guards to
  reproduce (root files are not `.jinja`).
- **No copier toggle / no `copier.yml` change** — the dogfood mirrors what
  ships; scanner versions are literals (mise pin / `uvx @X.Y.Z`), not copier
  variables.

## Acceptance

Run the **history scan locally first** — it has never run on this repo, and a
real historical secret or false positive would turn the PR red. Install the pin,
then run both tools green before wiring CI:

```bash
mise install gitleaks                    # realize the new mise.toml pin
mise exec -- just scan                   # semgrep (no-eval) + gitleaks full-history
```

Expected: semgrep `Targets scanned: 0` / `0 findings` / exit 0 (`tests/` is
semgrep-default-ignored and there is no `src/`); gitleaks `161 commits scanned` /
`no leaks found` / exit 0. Run via `mise exec` so the recipe's bare `gitleaks`
resolves in a non-mise-activated shell.

Then confirm the tree is otherwise unchanged. No `test_generation.py` change is
owed (root files, not `template/`). **No CHANGELOG `[Unreleased]` entry and no
version tag** — this touches zero `template/` files, so it is a maintainer-harness
change, not a template release (per AGENTS.md's tag-only-on-`template/`-facing
releases discipline).

## Out of scope / tracked follow-up

- **pip-audit (gap #5)** — shares the template `scan.yml`; will add one
  `pip-audit` step to the `scan` job created here plus a `just audit` recipe
  (dropping `--no-dev`, since `package=false` makes the template's `--no-dev`
  export vacuous). Separate PR.
- **Root-vs-template pin-parity test** — a real governance gap (semgrep/gitleaks
  pins are unguarded here), but it belongs to gap #4 (policy-tests), which reads
  the maintainer root and asserts config-literals cannot be silently weakened.
  Deferred there; covered in the interim by the AGENTS.md manual-sync note.
- **Aggregate `just ci` (gap #3)** — if added later, keep `scan` off it (CI-only,
  like the template).
- **Drop semgrep as not-applicable** — a defensible alternative: semgrep scans 0
  files here, the same reasoning the audit used to skip mutmut/coverage (no
  product code). Kept instead as a byte-parity forward guard to preserve the
  single `enable_scanners` mirror; revisit at PR review if an inert gate is
  unwanted (trivial reversal: delete `.semgrep.yml`, the semgrep recipe line, and
  the CI semgrep step).

## Explicit no-touch (guard rails)

- `copier.yml` — governs the generated template only; no scanner answers/defaults.
- `CHANGELOG.md` — no entry; this is not a template release (no tag either).
- `.pre-commit-config.yaml` — the template ships scanners CI-only (no scanner
  pre-commit hook); do **not** add a gitleaks/semgrep hook.
- `pyproject.toml` — no dep (semgrep/gitleaks run via uvx/mise, like zizmor).
- The zizmor job / its `1.26.1` pin / the template `scan.yml` — untouched.

## Endorsed decisions (verified in review — do not reopen)

`.gitleaks.toml` / `.semgrep.yml` bytes match the template verbatim; SHA
`e6a8b39…` is authentic `jdx/mise-action` v4.2.0; semgrep scans 0 files today
(`tests/` default-ignored, no `src/`) so it is green vacuously — kept as a
byte-parity forward guard; gitleaks scanned 161 commits clean; `fetch-depth: 0`
is required for the history scan; gitleaks-via-mise
and semgrep-via-uvx match the template's run mechanisms; `scan` off any aggregate
mirrors the template; the maintainer shell activates mise so bare `gitleaks`
resolves locally; the mirror is ROOT-only, so no generation test is owed.
