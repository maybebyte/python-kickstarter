# Dogfooding-gap audit — python-kickstarter (2026-07-01)

## 1. Executive summary

python-kickstarter is a Copier template whose entire value proposition is the guardrail suite it forces on every downstream project — yet several of those gates never run on the maintainer repo that ships them. The substantive code gates are fine: ruff (`select=["ALL"]`), basedpyright (`recommended`, `failOnWarnings`), pytest (OS matrix), and zizmor (workflow audit) all already run on this tree, and mise pins the toolchain identically to what it ships. What is missing is the rest of the shipped stack: **pre-commit (the flagged priority — the only always-on, non-toggleable gate besides lint/type/test, and it runs in zero surfaces here)**, secret + SAST scanning (gitleaks/semgrep), the dependency-advisory audit, the policy "gates-can't-be-weakened" suite, Renovate, an aggregate `just ci`, plus the trivial `.editorconfig` and half of the SHA-pin policy. Nine gaps are confirmed (seven fully missing, two partial); only one (gitleaks/semgrep) is a genuine security hole, so most of the remainder is hygiene-and-credibility rather than correctness risk. The governing principle throughout: dogfooding should **mirror** what the template already ships, not invent a divergent maintainer-only variant.

## 2. Already dogfooded (checked, no action)

- **pytest** — CI `test` job (OS matrix) + `just test`; the full generation harness.
- **zizmor 1.26.1** — CI `zizmor` job runs `uvx zizmor@1.26.1 --persona=regular .` over the maintainer's own workflows (SHA-pinning, permissions, injection).
- **basedpyright** — CI `typecheck` job + `just typecheck`; `mode=recommended`, `failOnWarnings=true`, `include=["tests"]`, `exclude=["template"]`.
- **ruff `select=["ALL"]`** — CI `lint` job (`ruff check .` + `ruff format --check .`) + `just lint`/`fmt`/`fmt-check`; config-level ignores only, no inline `# noqa`.
- **mise pinned toolchain** — root `mise.toml` pins python/uv/just/copier at byte-identical versions to `template/mise.toml.jinja`; the only unpinned template tool (gitleaks) is correctly omitted because gitleaks isn't used here (see gap #2).

## 3. Confirmed gaps

Ordered by priority then effort; **pre-commit surfaced first as the flagged priority** (the flagship always-on gate). Only `missing`/`partial` shown.

| # | Guardrail | Status | Priority | Effort | What to wire |
|---|-----------|--------|----------|--------|--------------|
| 1 | **pre-commit** (framework + config + git-hook path + hygiene/forbid-rej hooks) | missing | medium | small | dev dep `pre-commit>=4,<5`; root `.pre-commit-config.yaml` (`exclude:'^template/'`); `just precommit`; CI `pre-commit` job |
| 2 | **secret + SAST scanners** (gitleaks + semgrep) | missing | **high** | small | root `.gitleaks.toml` + `.semgrep.yml`; `gitleaks=8.30.1` in mise; `just scan`; CI `scan` job (history scan) |
| 3 | **aggregate `just ci`** recipe (+ `verify: ci`) | partial | medium | trivial | one recipe `ci: fmt-check lint typecheck test`; update AGENTS.md snapshot note |
| 4 | **policy-tests** (config-literals can't be silently weakened) | missing | medium | small | `tests/policy/test_gates.py` (stdlib); `just policy`; runs under existing `test` job |
| 5 | **dependency-audit** (pip-audit) | missing | medium | small | `just audit` (drop `--no-dev`); CI `audit` job; `uvx pip-audit@2.10.1` |
| 6 | **renovate** (dependency updates) | missing | medium | small | scoped root `renovate.json`; enable Mend app (operator step) |
| 7 | **editorconfig** | missing | low | trivial | copy `template/.editorconfig` verbatim to root |
| 8 | **sha-pin-policy** (offline SHA + tag-comment gate) | partial | low | small | closes for free with gap #4 — add `test_actions_are_sha_pinned()` |
| 9 | **property-tests** (hypothesis) | missing | low | medium | dev dep `hypothesis>=6`; register `property` marker; `tests/property/`; `just fuzz` (no `--no-cov`); CI `fuzz` job |

## 4. Per-gap detail

### Gap 1 — pre-commit (missing, medium) — FLAGGED

**Template forces downstream:** `template/.pre-commit-config.yaml.jinja` is emitted **unconditionally** into every downstream (no `enable_precommit` toggle; only the hidden `enable_precommit_install` gates the copy-time `uv run pre-commit install --install-hooks` in `copier.yml` `_tasks`). It pins `pre-commit-hooks` v6.0.0 (check-merge-conflict `--assume-in-merge`, end-of-file-fixer, trailing-whitespace), `ruff-pre-commit` v0.15.18, and local hooks (basedpyright + pytest on pre-push, forbid-rej fail hook on `\.rej$`). `test_generation.py` asserts the rendered downstream's config validates and passes `run --all-files`.

**Why it's a gap:** zero pre-commit surface on the maintainer tree — no root config, not in dev deps, no recipe, no CI. Every pre-commit reference outside `template/` targets the rendered downstream. The individual tools (ruff/basedpyright/pytest) running separately does **not** make the *layer* present: the framework, git-hook path, and four hooks that nothing else covers (end-of-file-fixer, trailing-whitespace, check-merge-conflict, forbid-rej) are entirely absent. This is the one always-on, non-toggleable flagship gate the maintainer skips — a visible "we don't eat our own dogfood."

**Wiring:**
- `pyproject.toml [dependency-groups] dev`: add `pre-commit>=4,<5` (mirrors `minimum_pre_commit_version 4.0.0`), then `uv lock` + `uv sync`.
- Root `.pre-commit-config.yaml` mirroring the template but scoped to the maintainer surface: SHA-pin each `rev:` with an exact-tag comment (AGENTS.md NEVER rule); the hygiene hooks **must** carry `exclude:'^template/'` (parity with `extend-exclude=["template"]`; `copier.yml` sets `keep_trailing_newline:true`, so template whitespace is deliberate). **Retarget the pytest/basedpyright local hooks** — the template's hook runs `pytest -m "not property" tests/unit`, but the maintainer has no `tests/unit`; its `tests/` is the flat generation harness, so point the hooks at the real layout.
- `justfile`: `precommit:` → `uv run pre-commit run --all-files`.
- CI: a `pre-commit` job in `test-template.yml` modeled on `lint`/`typecheck` (`uv sync --locked`, then `uv run pre-commit run --all-files --show-diff-on-failure`); stays inside the workflow zizmor already audits.
- Fix any trailing-whitespace / missing-final-newline findings in the same commit so the gate is green from the start. No mise pin (ships via dev deps like ruff/basedpyright).

**Risk if skipped:** hygiene failures unique to pre-commit (trailing whitespace, missing final newlines, merge-conflict markers, stray `.rej` files) plus drift in the shipped config's own hook revs go unenforced; the substantive checks are already covered in CI, so the loss is credibility + hygiene, not code-quality — hence medium, not high.

### Gap 2 — secret + SAST scanners: gitleaks + semgrep (missing, high)

**Template forces downstream:** `enable_scanners` (default true) emits `.gitleaks.toml` (extend-default), `.semgrep.yml` (Python no-eval ERROR rule), a `gitleaks=8.30.1` mise pin, a `just scan` recipe (semgrep + `gitleaks dir .`), and a **blocking** `scan.yml` CI job — semgrep via `uvx semgrep@1.167.0 ... --error`, gitleaks via `jdx/mise-action` + `mise exec -- gitleaks git . --redact --exit-code 1` with `fetch-depth:0` (full-history scan, deliberately catching committed-then-deleted secrets).

**Why it's a gap:** neither tool runs in any maintainer surface. This is **not** launderable through the existing zizmor job — zizmor audits GitHub Actions workflow files, which is orthogonal to secret scanning and Python SAST. Both genuinely apply: gitleaks is language-agnostic over the git history/working tree; semgrep's no-eval rule targets Python and `tests/` is a valid, non-circular SAST target. This is the only confirmed gap with a substantive security payload: a secret committed (even then deleted) to the maintainer repo would go uncaught by the very tool it ships, and it is the cheapest, most universal gate to adopt.

**Wiring:**
- Root `.gitleaks.toml` (`[extend] useDefault=true`) and `.semgrep.yml` (reuse the shipped no-eval rule so `tests/` is scanned).
- `mise.toml [tools]`: `gitleaks = "8.30.1"` (single source of truth, matching the template).
- `justfile`: `scan:` → `uvx semgrep@1.167.0 scan --config .semgrep.yml --metrics=off --error .` then `gitleaks git . --redact --exit-code 1` (history parity with CI; the template's local recipe uses `gitleaks dir`, but this repo already ships history-scanning CI as the stronger form).
- CI: a `scan` job modeled on `zizmor` — `checkout` (`fetch-depth:0`, `persist-credentials:false`), `setup-uv` 0.11.23, the semgrep step, and gitleaks via `jdx/mise-action` (`install:false`, **SHA-pinned with exact-tag comment** per the NEVER rule). Keep versions identical to what ships (semgrep 1.167.0, gitleaks 8.30.1).

**Risk if skipped:** an accidental secret in the maintainer repo or its history is undetected by its own shipped tool, and the shipped SAST rule is never validated against real Python — conspicuous next to the already-dogfooded zizmor/ruff/basedpyright/pytest.

### Gap 3 — aggregate `just ci` recipe (partial, medium)

**Template forces downstream:** `template/justfile.jinja` ships `ci: fmt-check lint typecheck test` (+ conditional `fuzz`/`policy`/`audit`) ending `@echo "ci: all gates passed"`, plus `verify: ci`. The harness gates each rendered project by invoking its `just ci`.

**Why it's partial (not missing):** every gate the aggregate would chain already runs here — four standalone recipes locally and four PR-blocking CI jobs (test/zizmor/typecheck/lint). Only the unified entry point is absent; AGENTS.md itself documents "There is NO aggregate `ci` recipe." Nothing escapes the gate, so the cost is ergonomics + the flagship "run `just ci` and you're green" promise the template's whole justfile is organized around.

**Wiring:** add `ci: fmt-check lint typecheck test` (+ `@echo`) and optionally `verify: ci`; keep zizmor a CI-only job (analogous to the template keeping scanners in `scan.yml` out of `ci`); update the AGENTS.md snapshot note. **Caveat (verifier):** downstream `test` is the fast `pytest -m "not property" tests/unit`, but the maintainer's `test` is the full generation matrix (slow, fills the 4G tmpfs per the memory notes), so a maintainer `just ci` chaining `test` is heavyweight — consider also a fast `check: fmt-check lint typecheck` split. No dep/mise/CI change needed.

**Risk if skipped:** low functional risk; credibility + drift between the individual recipes and the shipped aggregate ordering.

### Gap 4 — policy-tests: gates can't be silently weakened (missing, medium)

**Template forces downstream:** `enable_policy_tests` renders a stdlib-only (`tomllib`/`re`/`pathlib`) suite reading the project's own `pyproject.toml`/`justfile`/`AGENTS.md`/`.github/workflows` and asserting: coverage `fail_under >= coverage_floor`; basedpyright `== "recommended"`; `"ALL" in ruff select`; every `just <recipe>` referenced in AGENTS.md is a real recipe (docs-can't-lie); and every third-party `uses:` is `@<40-hex> # v<ver>`. Wired as `just policy` + a `ci` dependency.

**Why it's a gap:** the maintainer has every one of those gates but ships no self-pinning test — `test_generation.py`'s `test_typecheck_mode_is_recommended` and the ruff `"ALL"` assertion read the **rendered downstream** `pyproject.toml`, never ROOT. Flipping the maintainer's own basedpyright to `basic`, dropping `failOnWarnings`, narrowing ruff `select`, or referencing a nonexistent recipe would all keep CI green. The invariants are guarded today only by hand-written pyproject comments and AGENTS.md NEVER rules — exactly the human discipline this test mechanizes.

**Wiring:**
- `tests/policy/__init__.py` + `tests/policy/test_gates.py` (stdlib), ROOT = maintainer root. Assert `typeCheckingMode == "recommended"` **and** `failOnWarnings is True`; `"ALL" in ruff select`; port `test_actions_are_sha_pinned` verbatim (this also closes gap #8). **Omit** the `coverage_floor` pin (no coverage config / no src package — genuinely N/A).
- **Tune the docs-can't-lie regex:** the template's verbatim `just ([a-z][a-z-]*)` false-positives on AGENTS.md's prose mention of the downstream's `just ci` (the maintainer justfile has no `ci` recipe pre-#3); restrict matching to fenced command invocations so only real recipes are required.
- `justfile`: `policy:` → `uv run pytest tests/policy` (also auto-collected by `just test`, since `testpaths=["tests"]`). No new dep/mise pin.

**Verifier sharpening:** the SHA-pin sub-check overlaps the existing zizmor job (already the highest-security axis), so the *net-new* value is the three config-literals + docs-can't-lie, currently guarded only by comments and NEVER rules.

**Risk if skipped:** the meta-guardrail whose stated purpose is "gates cannot be silently weakened" is the one gate the maintainer doesn't self-enforce — a direct hit to the "practice what we ship" pitch.

### Gap 5 — dependency-audit: pip-audit (missing, medium)

**Template forces downstream:** `enable_dependency_audit` (default true) ships a `just audit` recipe (`uv export --frozen --no-emit-project --no-dev --no-hashes` → `uv run pip-audit -r ...`), folds `audit` into the blocking `just ci` chain, and adds a `pip-audit@2.10.1` step to `scan.yml`.

**Why it's a gap:** pip-audit runs zero times here — no recipe, no CI job/step, no dep, no AGENTS.md advisory command; the only documentation (the dependency-inventory spec) is `proposed`/unimplemented. It applies cleanly: the committed `uv.lock` resolves 28 packages (5 direct dev deps + transitives) and pip-audit audits exactly that graph — no runnable src needed, not circular.

**Wiring:**
- `justfile`: `audit:` → `uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt` / `uvx pip-audit@2.10.1 -r requirements-audit.txt` / `rm -f requirements-audit.txt`. **Drop `--no-dev`** — this is an *adaptation, not a weakening*: `package=false` + all deps under `[dependency-groups] dev` means the template's `--no-dev` export would be empty (vacuous exit-0); dropping it audits the whole graph (the spec's item 4 confirms this).
- CI: a standalone `audit` job (like `lint`/`typecheck`) — checkout + `setup-uv` 0.11.23 + the same export/audit. No pyproject dep (follow the "skip the pyproject dep for uvx-run tools" convention, like zizmor); keep the pin at 2.10.1 to match `scan.yml`.

**Caveat (verifier):** the maintainer's own (proposed) spec defers audit *recipes* in favor of a documented ad-hoc command; the full recipe + CI job is the maximal dogfood (technically sound), the lightest faithful close is documenting the advisory command. Impact is bounded (no shipped runtime package, so a CVE touches only the dev/CI machine) — hence medium, not high.

### Gap 6 — renovate (missing, medium)

**Template forces downstream:** `template/{% if enable_renovate %}renovate.json{% endif %}.jinja` (toggle default true) — a **config-only** artifact (no recipe, no CI job) consumed by the external Mend Renovate app: `extends:["config:recommended","helpers:pinGitHubActionDigests"]`, weekly `lockFileMaintenance`, `"pre-commit":{enabled:true}`, and a `customManager` for `uvx (semgrep|zizmor|pip-audit)@X.Y.Z`.

**Why it's a gap:** no root `renovate.json`; four live Renovate-trackable surfaces exist (uv deps + `uv.lock`, mise pins, Actions SHAs, the `uvx zizmor@1.26.1` run-step). The design spec flags this as "a dogfooding gap, like the typecheck/ruff dogfood gaps before it," citing concrete unsurfaced drift (copier 9.15.2→9.16.0, ruff 0.15.19→0.15.20, pydantic-core 2.46.4→2.47.0).

**Wiring (scoped per spec lines 198-211):**
- Root `renovate.json`: `config:recommended` + `helpers:pinGitHubActionDigests`, weekly `lockFileMaintenance`, and a `packageRules` entry `enabled:false` for depName `uv`.
- **Disable the `uv` manager** — the maintainer `uv` pin is multi-site (mise.toml + every `setup-uv version:` in the workflow) with no test asserting they agree, so Renovate would bump only mise.toml and silently desync the inputs.
- **Omit a `customManager` for `uvx` pins** — the only maintainer uvx pin is `zizmor@1.26.1`, parity-locked to the rendered template by `test_generation.py:797`; letting Renovate bump it would break that test. Omit the `pre-commit` manager unless gap #1 lands.
- **Operator precondition (required):** enable the Mend Renovate app on the repo — committing the JSON alone produces zero PRs. No recipe/CI/dep/mise wiring (hosted app; the template ships it config-only too).

**Risk if skipped:** the maintainer's deps drift unsupervised across all four pinned surfaces while it forces Renovate on downstreams. Lower-stakes than the enforcing gates (config-only, inert without the external app, non-blocking even downstream) — hence medium, not high.

### Gap 7 — editorconfig (missing, low)

**Template forces downstream:** `template/.editorconfig` shipped **verbatim and unconditionally** (no toggle) — `root=true`; `[*]` utf-8/lf/insert_final_newline/space-4; `[*.{yml,yaml,json,toml}]` indent 2. `test_generation.py:92-93` asserts its presence.

**Why it's a gap:** no root `.editorconfig`; the repo is full of files it governs (`tests/*.py`, plus 2-space YAML/TOML in pyproject/mise/copier/workflows). The template enforces it **passively** — no editorconfig-checker in its pre-commit/justfile/CI — so **full parity is met by just dropping the verbatim file at root** (values already match repo conventions; zero conflict). editorconfig-checker + a CI job would be optional hardening that *exceeds* template parity.

**Risk if skipped:** cosmetic — non-Python files ruff never touches can accrue inconsistent indentation/line-endings across editors; plus a "ships a file it doesn't carry" blemish. Least-central guardrail; low.

### Gap 8 — sha-pin-policy: offline SHA + tag-comment gate (partial, low)

**Template forces downstream:** two surfaces — (1) the zizmor `--persona=regular` step in `scan.yml` (enforces the SHA), and (2) when `enable_policy_tests` is also on, the offline `test_actions_are_sha_pinned()` requiring `uses: ...@<40-hex> # v<ver>` (SHA **plus** the tag comment), run in `just ci`/`just policy`.

**Why it's partial:** surface (1) is fully dogfooded — the maintainer's zizmor job is byte-identical and all 9 `uses:` lines are SHA-pinned with `# vX.Y.Z`. Surface (2) — the offline gate that enforces the *comment* (AGENTS.md NEVER rule #2) — is absent. **Priority downgraded medium→low (verifier disagreed with the original medium):** the security-load-bearing control (SHA pinning) is fully covered by zizmor; the missing test only checks the comment is *present and v-formatted*, **not that it matches the SHA's real tag** (accuracy is human-enforced downstream too, per the test's own docstring). Worst-case regression leaves the SHA correctly pinned and zizmor green — annotation-hygiene drift only. It is also a cross-product of two toggles; a downstream with `sha_pin_policy` but not `policy_tests` gets exactly the maintainer's config.

**Wiring:** **closes for free with gap #4** — port `test_actions_are_sha_pinned()` into `tests/policy/test_gates.py` (stdlib `re`+`pathlib`, `uses:\s*\S+@[0-9a-f]{40}\s+#\s*v\d+(\.\d+){0,2}\b`). Runs under the existing `test` job automatically. No dep/mise/CI change.

### Gap 9 — property-tests: hypothesis (missing, low)

**Template forces downstream:** `enable_property_tests` couples `hypothesis>=6`, a `@given` test over the shipped `clamp()`, a registered `property` marker (`--strict-markers`), and a `fuzz` recipe wired into `ci` and run in CI at `HYPOTHESIS_PROFILE=ci` (300 examples).

**Why it's a gap (but low):** hypothesis runs in zero maintainer surfaces. It *does* apply — the template's Jinja validators/escapers are the maintainer's product logic with real fuzzable invariants (`package_name` accept-set incl. control-char rejection, `coverage_floor` 1..100, the `replace('\\','\\\\')|replace('"','\\"')` TOML escaper round-tripping via `tomllib`). But those exact invariants are **already example-tested** (`test_control_chars_in_free_text_rejected`, `test_package_name_rejects_python_keywords`, `test_coverage_floor_out_of_range_is_rejected`, the quote/backslash round-trip test), so skipping it leaves no correctness hole — only forgone edge-case discovery. Weakest structural fit of any shipped gate (no algorithmic library src).

**Wiring:** add `hypothesis>=6` to dev deps; register the `property` marker (required — `addopts` carries `--strict-markers`); add `tests/property/` with `@given` tests against the real invariants; `just fuzz` mirroring the template **but without `--no-cov`** (no pytest-cov installed here); a CI `fuzz` job at `HYPOTHESIS_PROFILE=ci`. No mise change. **Caveat (verifier):** copier's `copier.yml` validators are Jinja evaluated at prompt time, not importable — fuzzing the *real* validators costs one copier render per example (slow); only the TOML escaper is cheaply drivable, and reimplementing its filter chain in-test risks testing a reimplementation. This reinforces low priority.

## 5. Not-applicable / deliberately skipped (considered, not missed)

- **mutation-tests (mutmut)** — *not-applicable.* Mutation testing structurally needs a code-under-test that a **separate** suite exercises. The product is Jinja (mutmut can't parse it); the only Python is the `~1171-line` generation harness (`tests/`). Pointing mutmut at `tests/` mutates the tests and re-runs those same tests as their own oracle — circular, zero signal. The template's config hard-codes `source_paths=["src/PKG"]` and `tests/unit`, neither of which exists here. Mutation is also non-gating even downstream (weekly cron, `continue-on-error`, absent from `ci`), so there is no gate to mirror. *Optional:* a one-line AGENTS.md note next to the Windows omission explaining why (doc nicety, not a gap).
- **coverage (`fail_under`/`coverage_floor`)** — *not-applicable.* No shipped runtime package (`package=false`, no `src/`); the policy suite (#4) correctly omits the coverage-floor assertion. There is no product code whose line coverage is meaningful.
- **property-tests** — considered applicable (see gap #9) but kept at low: the invariants are already example-tested and the structural fit is the weakest of any gate.

## 6. Net-new practices to consider

None of these is a current template toggle (all `in_template_today: false`), so **all are net-new**. Per the "mirror, don't diverge" principle, any one intended to run on the maintainer should first be added as a template layer (AGENTS.md 5-step: `enable_*` toggle → conditional `template/` file(s) → justfile/CI wiring → generation-test assertions), *then* dogfooded — except the maintainer-only/both-layer items noted below. Deduped and grouped:

**A. SHA-pin comment enforcement (three approaches to ONE invariant — pick one; extends confirmed gap #8, not net coverage):**
- *Verify/raise zizmor `ref-version-mismatch` coverage* (low) — the dep spec records that whether this audit fires under `--persona=regular` is **unverified**; verify the persona→audit mapping first, since it's zero-cost if `regular` already covers it.
- *`--persona=pedantic`* (medium) — mechanically enforces the tag-comment NEVER rule but adds triage noise (`stale-action-refs` is pedantic-only).
- *`pinact run --check`* (low) — the dedicated tool zizmor's own remediation docs name (mise-pinned, precise, no persona noise).
- *Recommendation:* verify `ref-version-mismatch` first; adopt `pinact --check` only if a real gap remains. Note none of these verify comment **accuracy** beyond format (that is human-enforced everywhere), consistent with gap #8's low priority.

**B. Workflow correctness — actionlint** (medium, net-new). Complements (does not duplicate) zizmor: shellcheck over `run:`, invalid `${{ }}`, bad matrix/`needs`/glob refs. Highest value pointed at the **rendered template workflows** inside `test_generation.py`, which today are only exercised via "does `just ci` pass," never statically lint. This repo's *product* is workflows, so it belongs in the template as a layer.

**C. Release & commit governance (the highest-value net-new cluster):**
- *Commit-message lint + no-AI-trailer guard* (high, net-new) — AGENTS.md/CLAUDE.md mandate Conventional Commits and the MEMORY note forbids `Co-Authored-By:.*Claude`/"Generated with", yet nothing enforces either. A `pull_request` commitlint job (or a `commit-msg` hook if gap #1 lands).
- *CHANGELOG-`[Unreleased]` PR check* (high, net-new) — fail if a PR touches `template/**`/`copier.yml`/`.github/workflows/**` but leaves `[Unreleased]` unchanged (with a `skip-changelog` escape hatch), making the documented release step executable.
- *Release-time tag + CHANGELOG validation* (low, net-new) — on `push: tags: v*`, assert the tag is annotated and a matching `## [x.y.z]` section + compare link exist; a light complement to full automation.
- *Release automation (release-please / git-cliff)* (medium, net-new) — because `copier update` targets the latest SemVer tag (not HEAD), a mis-cut tag silently ships in-progress commits downstream; automating tag+CHANGELOG promotion removes the hand-run checklist. Pairs with the commit-lint item.

**D. Supply-chain scoring — OpenSSF Scorecard** (low, net-new). The canonical scorecard for exactly the controls the template sells (pinned deps, token permissions, dangerous-workflow). Heavier (`id-token: write`, admin token for Branch-Protection); most valuable once public. The dep spec earmarks it as a deferred-not-rejected follow-up.

**E. Dependency visibility — `just deps` + AGENTS.md surface-map** (medium, net-new, **designed for both layers**). The fully-written spec (`docs/superpowers/specs/2026-06-25-dependency-inventory-design.md`, `status: proposed`) adds an unconditional `just deps` (`uv tree --frozen`) to both `template/justfile.jinja` and the maintainer justfile, a maintainer-only `just deps-template`, and a surface-map table enumerating every pin surface. Today only `uv.lock` is single-command-inspectable.

**F. Maintainer-only analogs (no template toggle needed — these are inherently maintainer-side):**
- *`_migrations`-required policy check* (medium, net-new) — a `tests/` case diffing `copier.yml` var names + `template/` paths against the latest tag; fail on a rename/move lacking a version-gated `_migrations` entry. This is the maintainer's own analog of the policy-tests meta-guardrail (gap #4) — a forgotten migration silently breaks every downstream `copier update`.
- *CI invokes the justfile recipes* (low, net-new — **extends confirmed gap #3**) — the generated `ci.yml.jinja` runs one command (`just ci`); the maintainer re-spells each gate inline (`uv run ruff check .`, `uv run basedpyright`, `uv run pytest`), so recipes and CI bodies are two copies that can drift. Fold into gap #3: have CI call `just lint`/`typecheck`/`test`/`ci` rather than duplicating them.

## 7. Recommended sequence

**Phase 1 — mirror existing template layers on the maintainer (each a single PR; the template already ships these, so no toggle work — just instantiate at root):**

1. **pre-commit** (gap #1) — flagged first; the flagship always-on gate. Land the config + dev dep + recipe + CI job, retargeting the pytest/basedpyright hooks and excluding `template/`. Fix any hygiene findings in the same PR.
2. **gitleaks + semgrep** (gap #2) — highest priority; the one substantive security win. Mirror both configs, the mise pin, `just scan`, and the history-scanning CI job.
3. **dependency-audit** (gap #5) — `just audit` (drop `--no-dev`) + CI job, `uvx pip-audit@2.10.1`.
4. **editorconfig** (gap #7) + **aggregate `just ci`** (gap #3) — bundle these two trivial wins; while adding `ci`, also point the CI jobs at the `just` recipes (candidate F/#3) so local == CI cannot drift. Note the slow-`test` caveat (consider a fast `check:` split).
5. **policy-tests** (gap #4) — `tests/policy/test_gates.py` with the tuned docs-can't-lie regex; this simultaneously **closes gap #8** (sha-pin offline gate) for free.
6. **renovate** (gap #6) — commit the scoped `renovate.json` **and** enable the Mend app (the JSON is inert without it); disable the `uv` manager and omit the `uvx`/`pre-commit` managers.
7. **property-tests** (gap #9) — lowest priority, weakest fit; do last, or defer.

**Phase 2 — net-new practices: add a copier toggle to the template FIRST, then dogfood (so the maintainer mirrors rather than diverges):**

8. **commit-message lint + no-AI-trailer** and **CHANGELOG-`[Unreleased]` PR check** (both high) — the highest-value net-new pair; add as template layers, then run on the maintainer.
9. **actionlint** (medium) — add as a template layer; point it at the rendered workflows in `test_generation.py` for the extra coverage win.
10. **SHA-pin comment enforcement** (Group A) — verify zizmor `ref-version-mismatch` under `--persona=regular` first (zero-cost); adopt `pinact --check` as a template layer only if a real gap survives.
11. **Release automation + release-time tag validation** (medium/low), then **Scorecard** (low, once public) — as template layers.

**Phase 3 — maintainer-only / both-layer (no template toggle gymnastics):**

12. **`just deps` + surface-map** (Group E) — implement the already-written spec; lands in both layers at once.
13. **`_migrations`-required policy check** (Group F) — a maintainer-side `tests/` guard on release safety.
