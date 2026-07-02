# Dogfood scanners (gitleaks + semgrep) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the template's `enable_scanners` layer (gitleaks + semgrep) onto the maintainer repo at root, green from the first commit, closing gap #2 of the dogfooding-gap audit.

**Architecture:** Five root files — two verbatim configs (`.gitleaks.toml`, `.semgrep.yml`), a `gitleaks` pin in `mise.toml`, an out-of-band `just scan` recipe, and a fifth `scan` job appended to the existing `.github/workflows/test-template.yml` (sibling to `zizmor`, not a separate `scan.yml`). Plus an `AGENTS.md` `## Scanning` section. No `template/` file is touched; no code, no dependency, no copier toggle.

**Tech Stack:** gitleaks 8.30.1 (via mise), semgrep 1.167.0 (via uvx), GitHub Actions, just, mise, uv.

**Design spec:** `docs/superpowers/specs/2026-07-01-dogfood-scanners-design.md` (approved; adversarially reviewed).

## Global Constraints

Copied verbatim from the spec; every task's requirements implicitly include these.

- **Exact pins (byte-identical to the template):** gitleaks `8.30.1`, semgrep `1.167.0`, setup-uv `0.11.23`. Action SHAs + exact-tag comments: `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0`, `astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0`, `jdx/mise-action@e6a8b3978addb5a52f2b4cd9d91eafa7f0ab959d # v4.2.0`.
- **NEVER** bump/introduce an Action SHA without its exact-tag comment (AGENTS.md NEVER rule #2).
- **NEVER** add a file under `template/` (AGENTS.md NEVER rule #1). All new files are ROOT — this rule does not fire, but do not touch the tested `template/` scanner files.
- **Do not touch** the `zizmor` job or its `1.26.1` pin; keep `zizmor` mentions in `test-template.yml` to its single pinned run-line (the drift-test regex `_versions_near('zizmor', …)` collects every `X.Y.Z` on any line containing `zizmor`).
- **Hermetic semgrep flags** `--config .semgrep.yml --metrics=off --error` — never `--config auto`.
- **gitleaks in CI** installs via `mise exec` from the `mise.toml` pin — never hardcode the version or a `releases/download` URL in the workflow.
- **Commits:** Conventional Commits; GPG-signed; **NO** Co-Authored-By / AI-attribution trailer; author `Ashlen <dev@anthes.is>`.
- **No release:** touches zero `template/` files → **no `CHANGELOG.md` entry, no version tag.**
- **No-touch:** `copier.yml`, `CHANGELOG.md`, `.pre-commit-config.yaml`, `pyproject.toml`.
- **Branch:** `chore/dogfood-scanners` (already created; spec already committed there as `fe9724f`).
- **Full-suite validation** (finishing): `TMPDIR=/home/user/.cache/kickstarter-test-tmp just test` (the 4G tmpfs `/tmp` is too small); ensure no untracked nested git repo under `.claude/worktrees/` first (copier `vcs_ref=HEAD` render hard-fails otherwise).

---

### Task 0: Commit the plan doc

**Files:**
- Commit: `docs/superpowers/plans/2026-07-01-dogfood-scanners.md`

The spec is already committed (`fe9724f`); commit this plan next so history reads spec → plan → feature work (matching the pre-commit precedent `0957475` → `a220409`). Inherits the Global Constraints (GPG-signed; NO AI trailer; author `Ashlen <dev@anthes.is>`).

- [ ] **Step 1: Commit the plan**

```bash
git add docs/superpowers/plans/2026-07-01-dogfood-scanners.md
git commit -m "docs(plans): add dogfood scanners implementation plan"
```

---

### Task 1: Scanner configs + mise pin + local `just scan` recipe

**Files:**
- Create: `.gitleaks.toml`
- Create: `.semgrep.yml`
- Modify: `mise.toml` (add gitleaks pin under `[tools]`)
- Modify: `justfile` (append `scan` recipe)

**Interfaces:**
- Produces: a working local `just scan` (semgrep no-eval over the tree + gitleaks full-history secret scan), and the `mise.toml` gitleaks pin the CI job (Task 2) installs from.

- [ ] **Step 1: Create `.gitleaks.toml`** (verbatim from `template/{% if enable_scanners %}.gitleaks.toml{% endif %}.jinja`)

```toml
# gitleaks config — extend the default ruleset.
[extend]
useDefault = true
```

- [ ] **Step 2: Create `.semgrep.yml`** (verbatim from the template)

```yaml
rules:
  - id: no-eval
    languages: [python]
    severity: ERROR
    message: Avoid eval(); it executes arbitrary code.
    pattern: eval(...)
```

- [ ] **Step 3: Add the gitleaks pin to `mise.toml`**

Append under `[tools]` (after `copier = "9.15.2"`), byte-identical to `template/mise.toml.jinja:8`:

```toml
gitleaks = "8.30.1"
```

Resulting `mise.toml`:

```toml
[tools]
python = "3.13"
uv = "0.11.23"
just = "1.50.0"
copier = "9.15.2"
gitleaks = "8.30.1"
```

- [ ] **Step 4: Append the `scan` recipe to `justfile`**

Add at end of file. The two command lines + inner comment are byte-identical to `template/justfile.jinja:48-50`; the header comment matches the maintainer's recipe-comment convention:

```just
# Out-of-band secret + SAST scan (semgrep + gitleaks); enforced in CI by the `scan` job, not `ci`.
scan:
    uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .
    # `git` (not `dir`): scan committed history like CI, catching secrets committed then deleted.
    gitleaks git . --redact --exit-code 1
```

- [ ] **Step 5: Realize the mise pin**

Run: `mise install gitleaks`
Expected: gitleaks 8.30.1 installed. Verify with `mise exec -- gitleaks version` (prints `8.30.1`). **Note:** `mise install` puts gitleaks on disk but does **not** add it to a non-interactive shell's PATH; a bare `gitleaks` resolves only in a mise-activated (interactive fish) shell, so verify and scan via `mise exec` below.

- [ ] **Step 6: Run the scan locally to verify it is green**

Run the scan in a mise-active way so the recipe's bare `gitleaks` resolves under the non-interactive executor shell:
Run: `mise exec -- just scan`
(Equivalently: `uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .` then `mise exec -- gitleaks git . --redact --exit-code 1`.)
Expected: semgrep prints `0 findings` (or no blocking findings) and exits 0 (the only `eval(` in `tests/` is a string literal at `tests/test_generation.py`, which the `eval(...)` Call pattern does not match); gitleaks prints `no leaks found` and exits 0.
**Failure taxonomy — classify before reacting:**
- `gitleaks: command not found` (exit 127) → PATH/activation issue, NOT a leak and NOT a network problem; re-run via `mise exec -- gitleaks …`.
- A real historical secret or a false-positive leak → **STOP and report**; do not suppress — this is exactly what the local-first run exists to catch.
- Network blocks `uvx`/`mise` downloads → note it, run whichever tool is reachable, defer the rest to the CI `scan` job (Task 2). Do not fake a pass.

- [ ] **Step 7: Verify pre-commit hygiene on the new files**

Run: `git add .gitleaks.toml .semgrep.yml mise.toml justfile && uv run pre-commit run --all-files`
Expected: all commit-stage hooks pass (the new YAML/TOML have final newlines and no trailing whitespace; `just`/`toml`/`yaml` are not python so ruff skips them). Stage only these four files — do **not** `git add -A` (the untracked spec/plan docs are committed separately).

- [ ] **Step 8: Commit**

```bash
git add .gitleaks.toml .semgrep.yml mise.toml justfile
git commit -m "feat(scan): dogfood gitleaks + semgrep configs, mise pin, just scan recipe"
```

---

### Task 2: CI `scan` job

**Files:**
- Modify: `.github/workflows/test-template.yml` (append a 5th job)

**Interfaces:**
- Consumes: the `mise.toml` gitleaks pin from Task 1 (installed via `mise exec`), and `.gitleaks.toml` / `.semgrep.yml`.
- Produces: a blocking PR gate mirroring the template's `scan.yml` steps, adapted to the maintainer's single-workflow layout.

- [ ] **Step 1: Append the `scan` job**

Add after the `lint` job (end of file), indented as a sibling under `jobs:`:

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

- [ ] **Step 2: Verify the zizmor-version drift test still passes**

Run: `uv run pytest tests/test_generation.py::test_tool_version_pins_have_no_drift -q`
Expected: PASS — the new `scan` job introduces a `semgrep` line but no `zizmor` token, so the zizmor version set stays `{1.26.1}` on both the maintainer file and the rendered `scan.yml`. (This test regex-scans the file as text; it does **not** parse the YAML — see Step 2b.)

- [ ] **Step 2b: Verify the workflow still parses as YAML (network-free)**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/test-template.yml').read_text())"`
Expected: exits 0 with no output — the appended `scan` job is well-formed YAML at the correct 2-space job indentation. A paste/indentation error fails here immediately, without needing the network (unlike the zizmor gate in Step 3).

- [ ] **Step 3: Verify the new job is zizmor-clean (the same audit CI's existing zizmor job runs)**

Run: `uvx zizmor@1.26.1 --persona=regular .`
Expected: PASS (no findings). The scan job is fully SHA-pinned, sets `persist-credentials: false`, has no injectable `${{ … }}` in `run:` blocks, and adds no elevated permissions.
**If network blocks `uvx`:** note it; the existing CI `zizmor` job will run this check on the PR.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test-template.yml
git commit -m "ci(scan): add gitleaks + semgrep scan job to test-template workflow"
```

---

### Task 3: `AGENTS.md` `## Scanning` section

**Files:**
- Modify: `AGENTS.md` (insert a new H2 after `## Pre-commit`, before `## Add a guardrail layer`)

**Interfaces:**
- Consumes: nothing runtime; documents Tasks 1–2 and records the manual pin-sync obligation (the sole drift guard — there is no Renovate here).

- [ ] **Step 1: Insert the `## Scanning` section**

Immediately after the `## Pre-commit` section's last paragraph (the "bump both `rev:` pins together" line) and before `## Add a guardrail layer`, insert the following (match AGENTS.md's house style — **one unwrapped line per prose paragraph**, as the existing sections do; the hard-wrapping shown here is only for plan readability):

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
+ `mise exec`; semgrep runs via `uvx semgrep@1.167.0` (no dep, like zizmor). The
semgrep rule is Python-only, so `tests/` is the effective target (`template/` is
Jinja; there is no `src/`); gitleaks scans the whole tree + history regardless of
language. Never pass semgrep `--config auto` (it drops the pinned rule and needs
metrics on); never hardcode the gitleaks version in CI (install via `mise exec`).

Deliberate divergences from the template's `scan.yml`
(`template/.github/workflows/…scan.yml….jinja`): the maintainer folds scanning
into the existing `test-template.yml` as a sibling `scan` job (the template
consolidates into a standalone `scan.yml`), matching the one-workflow / per-tool
layout and letting the existing zizmor job audit it; zizmor stays its own job
here rather than a step in `scan` (already dogfooded standalone). The CI
`mise-action` comment drops the template's "kept fresh by Renovate" note — **the
maintainer has no Renovate**, so the pins are static.

Because nothing here re-derives the pins (no Renovate; the generation drift test
reads only the *rendered* downstream), **bump every literal site by hand, against
the template.** gitleaks (`8.30.1`) has two maintainer sites — `mise.toml` and the
prose above — synced to `template/mise.toml.jinja` (CI installs via `mise exec`,
so there is no third gitleaks literal). semgrep (`1.167.0`) has three — the
`just scan` recipe, the `scan` job in `test-template.yml`, and the prose above —
synced to `template/justfile.jinja` and the template `scan.yml`. (Mirrors the
pre-commit "bump both `rev:` pins together" obligation.)
````

- [ ] **Step 2: Verify pre-commit hygiene**

Run: `git add AGENTS.md && uv run pre-commit run --all-files`
Expected: PASS (final newline present, no trailing whitespace; the embedded fenced ```` ```bash ```` block is fine — `AGENTS.md` is not under `template/`, so the eof/trailing-whitespace hooks apply and must be clean).

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): document the scan gate and pin-sync obligation"
```

---

### Finishing

- [ ] **Step 1: Run the full generation matrix** (unaffected by root-only changes, but confirm no regression)

Ensure no untracked `.claude/worktrees/` nested repo exists, then:
Run: `TMPDIR=/home/user/.cache/kickstarter-test-tmp just test`
Expected: all tests pass (root scanner files are outside `template/`, so the matrix is untouched; this confirms the `test-template.yml` edit didn't break the drift test).

- [ ] **Step 1b: Confirm the working tree is clean**

Run: `git status --porcelain`
Expected: empty — all feature files committed (Tasks 1–3), the plan doc committed (Task 0), no stray/untracked files. Do not open the PR with anything unexpected dangling.

- [ ] **Step 2: Finish the branch** — REQUIRED SUB-SKILL: superpowers:finishing-a-development-branch. Present push + PR options (operator-gated: pushing and opening the PR is the user's call). PR body via the pr-descriptions skill.

## Self-Review

- **Spec coverage:** configs (T1 s1–2), mise pin (T1 s3), recipe (T1 s4), local-green acceptance (T1 s5–6), CI job (T2), AGENTS.md incl. the enumerated pin-sync note (T3), no-tag/no-CHANGELOG (Global Constraints), no-touch guards (Global Constraints). All covered.
- **Placeholders:** none — every file's exact content is inline.
- **Type/name consistency:** SHAs, versions, and flags are identical across Global Constraints, T1, T2, and T3, and match the spec and the template ground truth.
