# Dogfood pre-commit — design (2026-07-01)

## Goal

Run the same *class* of pre-commit gate the template ships on the maintainer
repo itself, adapted to the maintainer's actual surface (`tests/` only, a slow
generation-matrix suite, ruff pinned via `uv.lock`), green from the first
commit. This closes gap #1 of the dogfooding-gap audit
(`docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md`).

This design was adversarially reviewed before writing; the config is unchanged
from the reviewed proposal and the review's amendments are folded into the
wiring and documentation below. Zero blockers; the tracked tree starts green
(no trailing-whitespace / missing-final-newline / conflict-marker / `.rej`
findings today).

## Decisions

Three forks were resolved with the maintainer:

1. **pytest hook: dropped.** The template's pytest hook runs
   `pytest -m "not property" tests/unit`, but the maintainer has no
   `tests/unit`, no `property` marker, and its only suite is the full
   generation matrix (slow; disk-hungry enough to need a `TMPDIR` override;
   needs `vcs_ref=HEAD`). CI's `test` job (3 Python × 2 OS) is the enforcer.
2. **ruff: local `uv run ruff` hooks**, not the `astral-sh/ruff-pre-commit`
   repo. Single source of truth = the locked ruff `0.15.19` that `just lint`
   and CI already use; `ruff-pre-commit` pins `0.15.18`, which would drift and
   could reformat in a way CI's `ruff format --check` then rejects. Consistent
   with how basedpyright already runs as a `uv run` local hook.
3. **CI: local-only (no CI job).** Mirrors the template exactly — downstream CI
   runs `just ci`, which never invokes pre-commit. The substantive checks
   (ruff, basedpyright) are already CI-enforced by the existing `lint` and
   `typecheck` jobs; the hygiene hooks stay a local gate.

## The config — `.pre-commit-config.yaml` (repo root)

```yaml
minimum_pre_commit_version: "4.0.0"
default_install_hook_types: [pre-commit, pre-push]
default_stages: [pre-commit]

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c  # v6.0.0
    hooks:
      - id: check-merge-conflict
        args: [--assume-in-merge]
      - id: end-of-file-fixer
        exclude: '^template/'
      - id: trailing-whitespace
        exclude: '^template/'

  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check (--fix)
        entry: uv run ruff check --fix --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: basedpyright
        name: basedpyright (type check)
        entry: uv run basedpyright
        language: system
        types: [python]
        pass_filenames: false
        stages: [pre-push]
      - id: forbid-rej
        name: forbid copier .rej conflict files
        entry: "unresolved copier .rej conflict files present; resolve and delete them"
        language: fail
        files: '\.rej$'
```

## Wiring

### `pyproject.toml`
Add `pre-commit>=4,<5` (mirrors `minimum_pre_commit_version: "4.0.0"`) to
`[dependency-groups] dev`, then `uv lock` + `uv sync`.

### `justfile`
Add a bootstrap recipe (the maintainer is **not** a copier-generated project,
so the copy-time `_tasks` `pre-commit install` never runs for it — without a
bootstrap path the hooks may never get installed), and a `precommit` recipe
that runs **both** hook stages (a bare `pre-commit run --all-files` is
commit-stage only and would silently skip the pre-push basedpyright hook):

```just
# one-time: sync the venv and install the git hooks (maintainer is not copier-generated)
setup:
    uv sync
    uv run pre-commit install

# run every hook over the whole tree: commit-stage hooks, then pre-push basedpyright
precommit:
    uv run pre-commit run --all-files
    uv run pre-commit run --all-files --hook-stage pre-push
```

The second `precommit` line runs basedpyright plus `end-of-file-fixer` /
`trailing-whitespace` (the two fixers inherit a `pre-push` stage from the pinned
`pre-commit-hooks` v6.0.0 manifest; ruff / check-merge-conflict / forbid-rej are
commit-stage only). The fixers therefore run in both lines — harmless on a clean
tree (idempotent) — and basedpyright duplicates `just typecheck`, which is
acceptable. `precommit` is **not** added to any aggregate `ci` recipe — when gap
#3's `just ci` lands, keep the mutating pre-commit hooks out of it.

### `AGENTS.md`
Add a new peer `## Pre-commit` H2 immediately after "Lint & format this repo".
It must not repeat the "CI enforces it" refrain (the hygiene hooks have no CI
backstop), must document the two divergences from what we ship, and must record
that the root and template `pre-commit-hooks` `rev:` pins move together:

````markdown
## Pre-commit

```bash
just setup      # one-time: sync the venv and install the git hooks
just precommit  # run every hook (commit-stage + pre-push basedpyright) over the whole tree
```

`pre-commit install` registers both git hooks (`default_install_hook_types:
[pre-commit, pre-push]`). On commit: ruff-check `--fix`, ruff-format,
end-of-file-fixer / trailing-whitespace (both `exclude: '^template/'` — template
Jinja whitespace is deliberate), check-merge-conflict, forbid-rej. On push:
end-of-file-fixer and trailing-whitespace also run (they inherit a `pre-push`
stage from the pinned `pre-commit-hooks` manifest, on any changed
non-`template/` text file), plus basedpyright when the push includes a `*.py`
file.

This is a **local-only** gate: there is no pre-commit CI job, matching the
template (whose downstream CI also never runs pre-commit). The ruff and
basedpyright *substance* is enforced by the existing `lint` and `typecheck` CI
jobs; the hygiene hooks (eof / trailing-whitespace / check-merge-conflict /
forbid-rej) have **no** CI backstop and are a local convenience here. A bare
`uv run pre-commit run --all-files` runs commit-stage hooks only — basedpyright
fires on push or via `just typecheck`; `just precommit` runs both.

Deliberate divergences from `template/.pre-commit-config.yaml.jinja`: ruff runs
via local `uv run ruff` hooks (locked 0.15.19) instead of the
`astral-sh/ruff-pre-commit` repo (pinned 0.15.18) — the venv is always synced
here, so there is no bootstrap reason to keep the isolated-env repo hook; the
pytest hook is dropped (the maintainer's only suite is the heavy generation
matrix — CI-only). The two configs share the SHA-pinned `pre-commit-hooks`
block: **bump both `rev:` pins together** (v6.0.0 = `3e8a8703…`).
````

## Documented divergences (mirror-except-where-surface-differs)

- **ruff local hooks** vs shipped `ruff-pre-commit` — eliminates the
  0.15.18/0.15.19 drift. Cost: the maintainer no longer exercises the
  `ruff-pre-commit` mechanism it ships; that mechanism is already covered by
  `test_generation.py`'s rendered `pre-commit run --all-files`, so no coverage
  is lost.
- **pytest dropped** — CI's matrix is the enforcer.
- **No downstream-style auto-install** — replaced by `just setup`.
- **`trailing-whitespace` has no `--markdown-linebreaks`** — omitted for
  template parity; be aware future two-space Markdown hard breaks get stripped.

## Acceptance

Stage the new file first (`--all-files` == `git ls-files`, so an unstaged new
config is invisible), then run both stages and confirm green:

```bash
git add -A
uv run pre-commit run --all-files                       # hygiene + ruff + forbid-rej
uv run pre-commit run --all-files --hook-stage pre-push # basedpyright
```

Fix any hygiene findings in the **same commit** so the gate starts green
(empirically the diff is currently empty). No CI job is added; no
`test_generation.py` change is owed (the maintainer's own config is not a
`template/` file, so the "every template file needs a generation-test" rule
does not fire). No CHANGELOG `[Unreleased]` entry (CHANGELOG is downstream /
template-scoped).

## Out of scope / tracked follow-up

- Aggregate `just ci` (gap #3) and any CI pre-commit job.
- **Reconcile the shipped `ruff-pre-commit` v0.15.18 pin with the locked ruff
  0.15.19 at the source** — this is a real *template* defect, not scope-free.
  The natural lever is a Renovate rule syncing the downstream `ruff-pre-commit`
  rev to the resolved ruff (the shipped `renovate.json` already enables the
  pre-commit manager), or evaluating moving the template's ruff to local hooks
  too (weighing the pre-`uv sync` bootstrap regression). File a template-level
  ticket.

## Endorsed decisions (verified in review — do not reopen)

SHA `3e8a8703…` is authentic `pre-commit-hooks` v6.0.0; `exclude: '^template/'`
on only the two mutating hygiene hooks is correct and sufficient;
check-merge-conflict is correctly not excluded; local ruff hooks resolve to
locked 0.15.19 and `.jinja` files never reach them (tagged jinja, not python);
dropping pytest is correct; basedpyright at pre-push mirrors the CI typecheck
job; `default_install_hook_types` means a single `pre-commit install` wires both
git hooks; local-only is the more faithful mirror; the tree starts green.
