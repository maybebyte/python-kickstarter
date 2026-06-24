# Agent contract — python-kickstarter (template maintainer)

This repo is a Copier template. `template/` holds the generated project as `.jinja`.

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
just fmt         # ruff format . + ruff check --fix . (apply safe fixes)
just fmt-check   # ruff format --check . (CI's format gate)
```

The maintainer harness runs the same full `select=["ALL"]` ruleset the template ships, scoped to `tests/` (the only Python surface; `template/` is Jinja). Every config-level ignore is load-bearing and audited — there are **no inline `# noqa`**. CI enforces `ruff check` + `ruff format --check` (the `lint` job in `.github/workflows/test-template.yml`).

## Add a guardrail layer

1. Add an `enable_*` toggle to `copier.yml`.
2. Add the conditional file(s) under `template/` (file: `{% if flag %}name{% endif %}.jinja`; dir: `{% if flag %}dir{% endif %}/`).
3. Wire it into `template/justfile.jinja` (recipe + `ci` dep). Then, where applicable: a dep in `template/pyproject.toml.jinja` (skip it for `uvx`-run tools like the scanners), a section in `template/AGENTS.md.jinja`, and a CI surface under `template/.github/workflows/` (a conditional step in `scan.yml`, or a dedicated conditional workflow file via the empty-name idiom).
4. Extend `tests/test_generation.py`: assert present-when-on AND absent-when-off, and that the layer's gate passes.

## Release

`copier update` targets the **latest SemVer git tag, not HEAD** — an untagged template makes every downstream update silently pull in-progress commits. The repo carries no tags until the first release is cut, so tag the released commit (on `main`) before announcing it or letting any downstream consume the template:

```bash
git tag -a v0.1.0 -m "v0.1.0"   # annotate the released commit
git push origin v0.1.0
git describe --tags             # verify a reachable tag now exists (must succeed)
```

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
