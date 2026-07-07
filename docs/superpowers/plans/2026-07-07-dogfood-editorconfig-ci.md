# Dogfood editorconfig + aggregate ci Implementation Plan

Design: `docs/superpowers/specs/2026-07-07-dogfood-editorconfig-ci-design.md`.
Closes Phase-1 item #4 (gap #7 editorconfig + gap #3 aggregate `just ci`) from
`docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md` §7.

## Global Constraints

- Branch `chore/dogfood-editorconfig-ci`, cut from `main` after PR #8 (dependency-audit) merged.
- Commits: Conventional Commits, GPG-signed, author `Ashlen <dev@anthes.is>`, **no** AI-attribution trailer.
- Mirror the template; document forced divergences. `audit` **is** a `ci` member (template chains it).
- No file under `template/`; no CI/dep/mise/CHANGELOG change; no inline `# noqa`.
- The full matrix (`just test`, hence `just ci`) needs a roomy `TMPDIR` (default 4G tmpfs `/tmp` overflows).

### Task 0: Commit the design spec + this plan

Add both docs under `docs/superpowers/{specs,plans}/2026-07-07-dogfood-editorconfig-ci*`.
Commit: `docs(plans): add dogfood editorconfig + aggregate ci design + plan`.

### Task 1: root `.editorconfig` (gap #7)

`cp template/.editorconfig .editorconfig` — byte-for-byte (11 lines, glob `[*.{yml,yaml,json}]`, trailing `\n`).
Verify identical: `diff template/.editorconfig .editorconfig` → no output.
No generation-test change (root file, not under `template/`).
Commit: `chore(editorconfig): dogfood the shipped .editorconfig at repo root`.

### Task 2: `ci` + `verify` recipe + audit-comment edit (gap #3) — justfile only

Insert after `default:` (before `# Run the template…` / `test:`):

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

Then fix the `audit` recipe's comment block (audit is now a `ci` member, so it is no longer "out-of-band"):
- header: `# Out-of-band dependency vulnerability audit: …` → `# Dependency vulnerability audit: …`
- CI-enforcement line: `# Enforced in CI by the `scan` job, not a `ci` recipe (there is none).` → `# Chained into `just ci` (mirrors the template) and independently enforced in CI by the `scan` job's pip-audit step.`

Leave `scan`'s comment unchanged (scan stays off `ci` — still true).
Commit: `feat(ci): dogfood aggregate 'just ci' + 'verify' recipe`.

### Task 3: AGENTS.md — new section + two live-site edits

1. New `## Run every gate (`just ci`)` section after the intro line (before `## Run the tests`). Contents per design §Wiring/AGENTS.md.
2. Rewrite the Dependency-audit section's stale `ci` wording: the `just audit` fence comment (drop "out-of-band", note it is a `just ci` member), `AGENTS.md:61` (out-of-band → chained into `just ci`), and `AGENTS.md:63` (drop "the maintainer has no `ci` recipe"; state audit is chained into `just ci` like the template).
Commit: `docs(agents): document 'just ci' (audit mirrored in, scanners CI-only)`.

### Finishing: full verification + PR

Run on a clean tree (roomy TMPDIR):
1. `TMPDIR=<roomy> just ci` → ends `ci: all gates passed` (subsumes a separate `just test`; audit needs network).
2. `just --show verify` → `verify: ci` (inspect, don't re-run the matrix).
3. `just precommit` → clean (eof/trailing-whitespace on the new `.editorconfig`, justfile, AGENTS.md).
4. `diff template/.editorconfig .editorconfig` → empty.
5. `grep -nF -e 'there is none' -e 'no `ci` recipe' justfile AGENTS.md` → empty, and `grep -ni 'out-of-band' justfile AGENTS.md` → only `scan`/generic references (audit no longer "out-of-band").
6. `git status --short` → empty; `requirements-audit.txt` absent.
7. zizmor N/A (no workflow touched) — state in PR.
Then push, open PR (base `main`), hand off merge to the operator.

## Self-review notes (author check against the spec)

- `audit` in `ci` (not dropped) — matches template L7. ✔
- `.editorconfig` verbatim, `{yml,yaml,json}` glob (no `toml`). ✔
- No `template/` file → no generation-test change. ✔
- All falsified live sites updated — `audit` recipe header + CI-enforcement comments, and the Dependency-audit fence + two prose clauses; `scan`'s "out-of-band"/"not `ci`" wording untouched (still true). ✔
- No `check:` split; candidate F deferred; dated docs frozen. ✔
- No CI/dep/mise/CHANGELOG change. ✔
