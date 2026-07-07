# Agent contract — python-kickstarter (template maintainer)

This repo is a Copier template. `template/` holds the generated project as `.jinja`.

## Run every gate (`just ci`)

```bash
just ci   # fmt-check + lint + typecheck + test + audit, then "ci: all gates passed"
```

`just ci` is the complete local gate — `ci: fmt-check lint typecheck test audit` ending `@echo "ci: all gates passed"`, with `verify` a bare alias (`verify: ci`). It **mirrors** `template/justfile.jinja`'s `ci`: the template chains `audit` when `enable_dependency_audit` is on (it is), so the faithful maintainer recipe includes it. `test` is the heavy generation matrix, so `just ci` needs a roomy `TMPDIR` — the default 4G tmpfs `/tmp` can overflow (export e.g. `TMPDIR=/path/to/roomy/dir` first). The fast inner loop is `just fmt-check lint typecheck` (one invocation, no matrix, no network); there is deliberately **no** `check:` recipe (the template ships none). `audit` is non-hermetic (it queries the OSV/PyPI advisory DB), so `just ci` reaches the network exactly as `just audit` does; scanners (`just scan`) deliberately stay **off** `ci` (CI-only), matching the template.

This maintainer `just ci` is distinct from the **downstream's** `just ci` referenced under "Run the tests": `just test` renders each project in the answer matrix and runs *its* `just ci` — a different, generated recipe.

CI does **not** run `just ci`. It keeps parallel per-gate jobs (`test`/`typecheck`/`lint`/`scan`), each inlining its command; only `test` fans out over the OS×Python matrix, and the `scan` job runs `uvx`/`mise exec` (not `uv run`); because every gate is enforced independently (audit via the `scan` job's `pip-audit` step), `just ci` here is the local reproduction of the PR gate, not the CI entry point. Pointing the CI jobs at these recipes (the gap-audit "candidate F") is deferred: the `scan` job aggregates pip-audit + semgrep + gitleaks as three steps that don't map onto the `audit`+`scan` recipe split, so it is a real restructure, not a one-line swap, and the follow-up must reconcile the recipe encoding with the parallel jobs.

**Forward-sync:** when the policy-tests (gap #4) and property-tests (gap #9) layers land, add `policy`/`fuzz` to **both** the `ci` recipe **and** this section, to keep mirroring the template's conditional `ci` (`fmt-check lint typecheck test{% if enable_property_tests %} fuzz{% endif %}{% if enable_policy_tests %} policy{% endif %}{% if enable_dependency_audit %} audit{% endif %}`).

Deliberate divergences from `template/justfile.jinja`'s `ci`: **none in the gate list** — `ci: fmt-check lint typecheck test audit`, `verify: ci`, and the `@echo` are exact. The divergences are structural: the maintainer's CI never runs `just ci` (parallel per-gate jobs — only `test` matrixed — with inline `uv run`/`uvx`/`mise exec` commands, vs the downstream `ci.yml`'s single `just ci`); there is no `check:` fast split (use `just fmt-check lint typecheck`); and candidate F is deferred. (The `audit` recipe's dropped `--no-dev` is a separate divergence documented under "Dependency audit", not a `ci`-list divergence.)

## Run the tests

```bash
uv sync
just test     # renders the answer matrix, installs each project, runs its `just ci`
```

## Type-check this repo

```bash
just typecheck   # basedpyright recommended over tests/ (the only Python surface; no src/)
```

The maintainer harness is held to the same `recommended` bar the template ships. CI enforces it (the `typecheck` job in `.github/workflows/test-template.yml`); `failOnWarnings` makes any finding fail the build.

## Lint & format this repo

```bash
just lint        # ruff check . — select=["ALL"] over tests/ (config-derived, audited ignores)
just fmt         # ruff check --fix . + ruff format . (apply safe fixes)
just fmt-check   # ruff format --check . (CI's format gate)
```

The maintainer harness runs the same full `select=["ALL"]` ruleset the template ships, scoped to `tests/` (the only Python surface; `template/` is Jinja). Every config-level ignore is load-bearing and audited — there are **no inline `# noqa`**. CI enforces `ruff check` + `ruff format --check` (the `lint` job in `.github/workflows/test-template.yml`).

## Pre-commit

```bash
just setup      # one-time: sync the venv and install the git hooks
just precommit  # run every hook (commit-stage + pre-push basedpyright) over the whole tree
```

`pre-commit install` registers both git hooks (`default_install_hook_types: [pre-commit, pre-push]`). On commit: ruff-check `--fix`, ruff-format, end-of-file-fixer / trailing-whitespace (both `exclude: '^template/'` — template Jinja whitespace is deliberate), check-merge-conflict, forbid-rej. On push: end-of-file-fixer and trailing-whitespace also run (they inherit a `pre-push` stage from the pinned `pre-commit-hooks` manifest, on any changed non-`template/` text file), plus basedpyright when the push includes a `*.py` file.

This is a **local-only** gate: there is no pre-commit CI job, matching the template (whose downstream CI also never runs pre-commit). The ruff and basedpyright *substance* is enforced by the existing `lint` and `typecheck` CI jobs; the hygiene hooks (eof / trailing-whitespace / check-merge-conflict / forbid-rej) have **no** CI backstop and are a local convenience here. A bare `uv run pre-commit run --all-files` runs commit-stage hooks only — basedpyright fires on push or via `just typecheck`; `just precommit` runs both.

Deliberate divergences from `template/.pre-commit-config.yaml.jinja`: ruff runs via local `uv run ruff` hooks (locked 0.15.19) instead of the `astral-sh/ruff-pre-commit` repo (pinned 0.15.18) — the venv is always synced here, so there is no bootstrap reason to keep the isolated-env repo hook; the pytest hook is dropped (the maintainer's only suite is the heavy generation matrix — CI-only). The two configs share the SHA-pinned `pre-commit-hooks` block: **bump both `rev:` pins together** (v6.0.0 = `3e8a8703…`).

## Scanning

```bash
just scan   # out-of-band secret + SAST scan: semgrep (no-eval) + gitleaks (full history)
```

`just scan` runs semgrep's `no-eval` rule and a gitleaks **full-history** secret scan (`.gitleaks.toml` = default ruleset). It is out-of-band (chained into no recipe), but CI enforces it: the `scan` job in `.github/workflows/test-template.yml` is a blocking PR gate. gitleaks is pinned in `mise.toml` (`gitleaks = "8.30.1"`) and installed in CI via `jdx/mise-action` + `mise exec`; semgrep runs via `uvx semgrep@1.167.0` (no dep, like zizmor). **semgrep scans non-test Python only** — its built-in `.semgrepignore` excludes `tests/`, and there is no `src/`, so on this repo it currently scans **0 files** (a forward guard that mirrors the shipped gate and fires the moment any non-test Python is added at root); gitleaks scans the whole tree + full history regardless of language and is the substantive gate here. Never pass semgrep `--config auto` (it drops the pinned rule and needs metrics on); never hardcode the gitleaks version in CI (install via `mise exec`).

Deliberate divergences from the template's `scan.yml` (`template/.github/workflows/…scan.yml….jinja`): the maintainer folds scanning into the existing `test-template.yml` as a sibling `scan` job (the template consolidates into a standalone `scan.yml`), matching the one-workflow / per-tool layout and letting the existing zizmor job audit it; zizmor stays its own job here rather than a step in `scan` (already dogfooded standalone). The CI `mise-action` comment drops the template's "kept fresh by Renovate" note — **the maintainer has no Renovate**, so the pins are static.

Because nothing here re-derives the pins (no Renovate; the generation drift test reads only the *rendered* downstream), **bump every literal site by hand, against the template.** gitleaks (`8.30.1`) has two maintainer sites — `mise.toml` and the prose above — synced to `template/mise.toml.jinja` (CI installs via `mise exec`, so there is no third gitleaks literal). semgrep (`1.167.0`) has three — the `just scan` recipe, the `scan` job in `test-template.yml`, and the prose above — synced to `template/justfile.jinja` and the template `scan.yml`. (Mirrors the pre-commit "bump both `rev:` pins together" obligation.)

## Dependency audit

```bash
just audit   # dependency vulnerability audit: pip-audit over the full locked graph (also a `just ci` member)
```

`just audit` exports the fully-resolved lockfile (`uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt`) and runs `uvx pip-audit@2.10.1 -r requirements-audit.txt`. It is chained into `just ci` (the local aggregate — see "Run every gate") and independently enforced in CI: the `pip-audit` step in the `scan` job of `.github/workflows/test-template.yml` is a blocking PR gate. Unlike semgrep — which scans 0 files here — pip-audit is the **substantive** dependency gate: it audits the real ~35-package dev+transitive graph (copier / pytest / ruff / basedpyright / pre-commit / plumbum / pyyaml + transitives), because **`--no-dev` is dropped**. Never restore `--no-dev`: `package = false` puts every dep in the dev group, so `--no-dev` would export 0 packages and pass vacuously. `requirements-audit.txt` is `rm`'d on success, gitignored, and lingers (harmlessly) only after a failed run. pip-audit is the one **non-hermetic** step in the `scan` job — it queries the OSV/PyPI advisory DB, so this gate can turn red on a newly-published CVE (or an advisory-DB outage) independent of any code change; a `--frozen` **export** failure instead means `uv.lock` is stale (re-lock), distinct from a pip-audit non-zero (a CVE). pip-audit runs via `uvx` (no pyproject dep, like semgrep/zizmor).

Deliberate divergences from the template's dependency-audit layer: `--no-dev` is dropped (above); pip-audit runs via `uvx pip-audit@2.10.1` in both the recipe and CI with **no** pyproject dep (the template adds `pip-audit>=2.10` to its dev group and runs `uv run pip-audit` locally); it is folded into `test-template.yml`'s `scan` job as a step (the template ships it in a standalone `scan.yml`); and, like the template, `audit` is chained into `just ci` (see "Run every gate") while additionally enforced in CI as the `pip-audit` step in the `scan` job.

Because nothing here re-derives the pin (no Renovate; the generation drift test reads only the *rendered* downstream), **bump every literal by hand, against the template.** pip-audit (`2.10.1`) has three maintainer sites — the `just audit` recipe, the `pip-audit` step in `test-template.yml`, and the prose above — synced to `template/.github/workflows/…scan.yml….jinja` (the only exact-version template site; the template justfile uses unpinned `uv run pip-audit` and template pyproject floors `pip-audit>=2.10`). No `mise.toml` or `pyproject.toml` pip-audit literal exists (uvx-run, unlike gitleaks). **Sync only the pin *value* — never the export flags:** the template's `uv export` keeps `--no-dev`, but the maintainer must not (it exports 0 packages here — see above), so a mechanical sync against the template would silently neuter the gate. (Mirrors the semgrep/gitleaks pin-sync note and the pre-commit "bump both `rev:` pins together" rule.)

## Add a guardrail layer

1. Add an `enable_*` toggle to `copier.yml`.
2. Add the conditional file(s) under `template/` (file: `{% if flag %}name{% endif %}.jinja`; dir: `{% if flag %}dir{% endif %}/`).
3. Wire it into `template/justfile.jinja` (a recipe; add it as a `ci` dep only for a *gating* layer — out-of-band checks like `scan`/`mutate` ship a recipe but stay off `ci`, and CI-only layers like renovate/sha-pin add no recipe at all). Then, where applicable: a dep in `template/pyproject.toml.jinja` (skip it for `uvx`-run tools like the scanners), a section in `template/AGENTS.md.jinja`, and a CI surface under `template/.github/workflows/` (a conditional step in `scan.yml`, or a dedicated conditional workflow file via the empty-name idiom).
4. Extend `tests/test_generation.py`: assert present-when-on AND absent-when-off, and that the layer's gate passes.

## Release

`copier update` targets the **latest SemVer git tag, not HEAD** — an untagged template makes every downstream update silently pull in-progress commits. Always tag each released commit (on `main`) before announcing it or letting any downstream consume the template (v0.1.0 was the first release):

```bash
git tag -a v0.1.0 -m "v0.1.0"   # annotate the released commit
git push origin v0.1.0
git describe --tags             # verify a reachable tag now exists (must succeed)
```

Update `CHANGELOG.md` (promote the `Unreleased` entries under the new version) in the release commit before tagging.

Breaking renames/moves need a version-gated `_migrations` entry.

## Updating a downstream project (operator preconditions)

`copier update` is a 3-way merge with three load-bearing preconditions:

1. A valid `.copier-answers.yml` in the destination (hand-editing it is unsupported).
2. A git-tagged template (updates target the latest SemVer tag, not HEAD).
3. A clean destination working tree.

`copier update --trust` is required (the template's `_tasks` — and any future `_migrations` — are "unsafe" features). Conflicts surface as inline markers and always need manual review.

## Windows omission

Windows is intentionally omitted from the CI matrix because mutmut requires `fork()`, which is not available on Windows outside WSL. If Windows support is wanted later, gate the mutation-running tests off `sys.platform`.

## NEVER

- Add a file under `template/` without a generation-test assertion.
- Bump an Action SHA without updating its exact-tag comment.
