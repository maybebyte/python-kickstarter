# Dogfood policy-tests (+ sha-pin offline gate) — design (2026-07-07)

## Goal

Close two Phase-1 dogfooding gaps from `docs/superpowers/plans/2026-07-01-dogfood-gap-audit.md`
§7 item #5 in one bundle:

- **Gap #4 — policy-tests.** `template/tests/{% if enable_policy_tests %}policy{% endif %}/test_gates.py.jinja`
  ships a stdlib-only suite that reads a downstream's own `pyproject.toml`/`justfile`/`AGENTS.md`/`.github/workflows`
  and asserts the gates cannot be silently weakened. The maintainer repo — whose whole pitch is that suite —
  does not run it on itself.
- **Gap #8 — sha-pin offline gate.** `test_actions_are_sha_pinned()` (gated on `enable_sha_pin_policy`, inside
  the same `test_gates.py`) enforces `uses: …@<40-hex> # v<ver>` offline. The maintainer's zizmor job already
  enforces the SHA (surface 1, fully dogfooded); the offline comment gate (surface 2) is absent. It **closes for
  free with gap #4** — porting the policy suite brings the sha-pin test along (both toggles default on).

Governing principle (as at every prior gap): **mirror the template; diverge only where the maintainer surface
forces it, and document each forced divergence in AGENTS.md.**

### Empirical anchors (verified against the tree, not roadmap prose)

- **The template's assertions** (`template/tests/…/test_gates.py.jinja`): coverage `fail_under >= coverage_floor`;
  `typeCheckingMode == "recommended"`; `"ALL" in ruff select` (when `ruff_ruleset == "all"`); docs-can't-lie
  (`re.findall(r"just ([a-z][a-z-]*)", AGENTS.md) <= justfile recipes`); and (when `enable_sha_pin_policy`)
  `test_actions_are_sha_pinned()`.
- **Maintainer `pyproject.toml` has no `[tool.coverage]`** and no `--cov` in `addopts` (`package = false`, no
  `src/`). The coverage-floor assertion has nothing to protect, and `--no-cov` (which the template's `policy`
  recipe and the generation test at `tests/test_generation.py:343` pass to the *downstream*) is an **invalid
  arg here** — no `pytest-cov` is installed.
- **Maintainer `pyproject.toml` pins the type gate's teeth explicitly**: `typeCheckingMode = "recommended"`
  (L35) **and** `failOnWarnings = true` (L36, with a comment: "pin it so a future mode/version drift … cannot
  silently un-fail the build"). A policy test asserting `failOnWarnings is True` is the natural enforcement of
  that stated intent.
- **Maintainer `ruff.lint.select = ["ALL"]`** (L50).
- **All 12 `uses:` lines** in `.github/workflows/test-template.yml` (4 distinct actions) are already
  `@<40-hex> # v<M.m.p>` — `test_actions_are_sha_pinned()` passes on the current tree unchanged.
- **`tests/test_generation.py` already asserts the template's policy layer** present-when-on/absent-when-off
  (`test_policy_layer` L340, `test_sha_pin_policy` L587, `test_sha_pin_audit_ships_without_policy_tests` L597,
  `test_coverage_floor_wiring` L785). This PR adds **maintainer-root** files, not `template/`
  files → **no generation-test obligation** and no `template/` change.
- **Maintainer AGENTS.md `just` tokens inside ```-fenced blocks** are all real recipes today (audit, ci, fmt,
  fmt-check, lint, precommit, scan, setup, test, typecheck). The maintainer's AGENTS.md **prose** is the one
  place that legitimately discusses *template-only* recipes (`fuzz`, `mutate`) — a downstream's AGENTS.md never
  does. (See D-REGEX.)

## Decisions

- **D1 — Drop the coverage-floor assertion.** No `[tool.coverage]` / no runtime package → nothing to protect
  (roadmap §140: "genuinely N/A"). **Surface-forced** divergence; documented.
- **D2 — Keep four assertions, add a fifth (unforced).** Port `test_type_checking_is_recommended`,
  `test_ruff_select_present`, the docs-can't-lie test, and `test_actions_are_sha_pinned` (gap #8). **Add**
  `test_type_checking_fails_on_warnings` asserting `failOnWarnings is True` — the maintainer pins this teeth
  explicitly (pyproject L36) and the policy suite exists precisely to stop such a pin being silently removed
  (roadmap §79). This is an **unforced** strengthening (the template ships *no* `failOnWarnings` assertion — the
  reviewers confirmed it), but it protects a real maintainer-only pin, so it is documented and **offered for
  sign-off** alongside D-REGEX.
- **D-REGEX — Tune docs-can't-lie to fenced-code-block invocations only.** THE key decision, and an **unforced,
  preventive** divergence — *not* surface-forced: the template's naive whole-doc regex `re.findall(r"just
  ([a-z][a-z-]*)", AGENTS.md)` **passes on the current tree** (`missing=[]`; every prose `just X` token today is a
  real recipe). The invariant fenced-only encodes is "every recipe I tell you to **run** exists," not "every
  recipe I **mention** exists." Rationale for diverging anyway: the maintainer's AGENTS.md is the one doc that
  will document template-only recipes in prose — the naive regex flips to **FAIL** the moment gap-#9's maintainer
  prose mirrors `template/AGENTS.md.jinja` L32/L36's verbatim `just fuzz` / `just mutate` wording (both confirmed
  present in the template). Fenced-only gates runnable examples and lets prose freely reference template recipes.
  **Costs / caveats:** it stops checking *inline-prose* `just <recipe>` references against recipe renames; it
  still scans `#` comments *inside* fences (so the discipline "no bare `just <template-recipe>` in a fenced block"
  remains); and `just --show` / multi-recipe lines fail **open** (only the first token per invocation is read).
  Two cases do **not** fail open, and both bit the plan's first draft:
  **(a) fence parity** — the extractor pairs triple-backtick runs *sequentially*, so an **odd** number of runs in
  AGENTS.md mispairs every fence after the offender and sweeps arbitrary prose into a "block". Writing the
  delimiter literally in prose — e.g. to *describe this very divergence* — is enough to trigger it, and the
  spurious block then harvests any prose `just <template-recipe>` token into `referenced` → hard **FAIL**.
  **(b) recipe-name shape** — the allowlist regex matches only `[a-z][a-z-]*`, so a future parametrized or
  underscored recipe cited in a fenced example would be absent from `recipes` → **false-positive**.
  Mitigations (now mandated in the plan's Global Constraints and in the shipped AGENTS.md section): never write a
  literal triple-backtick run in AGENTS.md prose, and never write a bare `just <name>` for a non-recipe anywhere in
  AGENTS.md — name it without the `just ` prefix. Plan Task 3 Step 6 adds a fence-parity guard.
  *Alternative — naive whole-doc mirror (exact template parity, checks all prose) + a standing "never write a bare
  `just <template-recipe>` in prose" discipline that breaks the moment gap #9 lands.* **This is the one call worth
  explicit sign-off.**
- **D3 — `policy` recipe + `ci` member; `test` stays bare.** Add `policy: uv run pytest tests/policy` (no
  `--no-cov` — D1's root cause). Chain it: `ci: fmt-check lint typecheck test policy audit` (mirrors the template's
  distinct `policy` member and honors the gap-#3 forward-sync note). Leave `test` as bare `uv run pytest`: it also
  auto-collects `tests/policy` (roadmap §81) — a redundant safety net and keeps `just test` ≡ the CI `test` job's
  inline command. The resulting stdlib millisecond re-run inside `just ci` is negligible. *Alternative —
  `test: … --ignore=tests/policy` for a clean template-style partition: rejected (YAGNI; the double-run is
  microseconds, and matching the CI command + the safety net is worth more).*
- **D4 — No CI / dep / mise / CHANGELOG change.** The CI `test` job runs bare `uv run pytest`, which already
  collects `tests/policy` → the gate is enforced in CI with **zero** workflow edit (roadmap §127). No new dep
  (stdlib only). CHANGELOG's `[Unreleased]` describes the *template product*; this PR dogfoods the maintainer
  surface only (consistent with gaps #1/#2/#3/#5).
- **D5 — `tests/policy/__init__.py` (empty).** The maintainer's `tests/` **is** a package (`tests/__init__.py`
  exists); the subpackage mirrors that layout (roadmap §79). Divergence from the template (which ships no
  `policy/__init__.py`), forced by the maintainer's package layout. Covered by the `tests/**` per-file-ignores
  (D104).
- **D6 — Sweep every `ci` gate-list site (reviewer-enumerated).** Adding `policy` lands half of the gap-#3
  forward-sync note's obligation. Same discipline as the gap-#3 "out-of-band" sweep. The **complete** site list
  (the reviewers found the design's original `grep 'test audit'` would have **missed** the `+`-form at
  AGENTS.md:8):
  - `justfile:11` — the recipe: `ci: fmt-check lint typecheck test audit` → `… test policy audit` (**the
    functional change**). The `ci` comment (L6–10) has **no** enumerated gate list to sync (prose names only
    `test`/`audit`); optionally mention `policy`.
  - `AGENTS.md:8` — **`+`-form fenced comment** `# fmt-check + lint + typecheck + test + audit` → insert
    `+ policy` before `+ audit`. (Missed by a `grep 'test audit'`; see the broadened acceptance grep.)
  - `AGENTS.md:11` — prose recipe reproduction `ci: fmt-check lint typecheck test audit` → `… test policy audit`.
  - `AGENTS.md:17` — the **forward-sync note**: reword prose to "when the property-tests (gap #9) layer lands, add
    `fuzz` …" (policy now landed). The **quoted template conditional string** (`test{% if enable_property_tests %}
    fuzz{% endif %}{% if enable_policy_tests %} policy{% endif %}…`) stays **verbatim** — it is the template's own
    literal and is already correct.
  - `AGENTS.md:19` — `ci: fmt-check lint typecheck test audit` inside the "none in the gate list" sentence →
    `… test policy audit`. The surrounding "**none in the gate list**" claim **stays true** (the template
    conditionally adds `policy` via `{% if enable_policy_tests %}`, which is on) — only the literal changes.

## Wiring

### `tests/policy/__init__.py` (new, empty)

Package marker; empty (D104 ignored under `tests/**`).

### `tests/policy/test_gates.py` (new, gap #4 + #8)

Stdlib only (`re`, `tomllib`, `pathlib`, `typing.cast`). `ROOT = Path(__file__).resolve().parent.parent.parent`
(→ maintainer root). Five tests:

1. `test_type_checking_is_recommended` — `PYPROJECT["tool"]["basedpyright"]["typeCheckingMode"] == "recommended"`.
2. `test_type_checking_fails_on_warnings` — `PYPROJECT["tool"]["basedpyright"]["failOnWarnings"] is True`. **(new; D2)**
3. `test_ruff_select_present` — `"ALL" in cast("list[str]", PYPROJECT["tool"]["ruff"]["lint"]["select"])`.
4. `test_agents_md_recipes_exist_in_justfile` — **fenced-only** (D-REGEX): extract ```-fenced blocks, collect
   `just ([a-z][a-z-]*)` within them, assert `referenced <= recipes` where `recipes` = `^([a-z][a-z-]*):` in the
   justfile. **Typecheck-passing form (mandatory — the reviewers' first draft failed basedpyright with 3
   `reportAny` warnings):** `blocks = cast("list[str]", re.findall(r"```.*?```", agents, re.DOTALL))` then an
   **annotated accumulator** loop `referenced: set[str] = set(); for block in blocks: referenced |= set(re.findall(…))`
   — **not** a bare set-comprehension (whose `block` is `Any`, tripping `reportAny` under `recommended` +
   `failOnWarnings`).
5. `test_actions_are_sha_pinned` — **verbatim** from the template: `uses:\s*\S+@([0-9a-f]{40})\s+#\s*v\d+(\.\d+){0,2}\b`
   over each `.github/workflows/*.yml` line starting `- uses:`/`uses:`. **(gap #8)**

Written to pass ruff `select=["ALL"]` (S101/PLR2004/D103 already ignored under `tests/**`) and basedpyright
`recommended` + `failOnWarnings` (module docstring, `-> None`, `cast` for the ruff list).

### `justfile` (gap #4)

Add immediately after the `test` recipe (mirroring the template's `test` → `policy` → `audit` relative order):

```just
# Policy gate: config-literal pins so the gates above cannot be silently weakened
# (stdlib-only; also auto-collected by `just test`). Mirrors template/justfile.jinja's `policy`.
policy:
    uv run pytest tests/policy
```

Change the `ci` recipe: `ci: fmt-check lint typecheck test policy audit` (insert `policy` before `audit`, matching
the template's `test{…} policy{…} audit` order). The `ci` comment (L6–10) has **no** enumerated gate list to keep
in sync (it names only `test`/`audit` in prose) — do not chase a nonexistent enumeration; optionally mention
`policy`.

### `AGENTS.md` (gap #4)

- New `## Policy gate (`just policy`)` section documenting: the five assertions; the dropped coverage floor and
  the added `failOnWarnings` pin (both keyed to the maintainer's real config); the fenced-only docs-can't-lie
  tuning **as a documented divergence**, plus the **two prose invariants** it requires (no literal triple-backtick
  run in prose; no bare `just <name>` for a non-recipe) and its **known limits** (recipe-name shape; CI wiring
  unguarded — candidate F); that `test_actions_are_sha_pinned` closes gap #8 and overlaps the zizmor
  job (net-new value = the config-literals + docs-can't-lie); `policy` as a `ci` member also auto-collected by
  `test`; the scope caveat (config *literals*, not the ruff ignore lists or recipe bodies); no CI/dep change.
- Sweep every `ci` gate-list site per **D6** (justfile:11; AGENTS.md:8 `+`-form, :11, :17 note, :19) — the
  complete reviewer-enumerated list is in D6.

## Documented divergences (mirror-except-where-surface-differs)

**Surface-forced (the maintainer surface makes the template idiom impossible/invalid):**
- **Coverage-floor assertion dropped** (D1) — no `[tool.coverage]`/no package; nothing to protect.
- **`--no-cov` dropped from the `policy` recipe** (D1 root cause) — no `pytest-cov`; the flag is invalid here
  (the template keeps it because the downstream has a global `--cov`).
- **`tests/policy/__init__.py` added** (D5) — the maintainer's `tests/` is a package; the template ships none.
- **`test` stays bare / double-collects** (D3) — the maintainer has no `tests/unit`; bare `test` keeps the CI
  command match + a safety net.

**Unforced (taste — *not* surface-forced; offered for explicit sign-off):**
- **`failOnWarnings is True` assertion added** (D2) — the template ships no such assertion; this strengthens a
  real maintainer-only pin (pyproject L36). Keep-recommended.
- **Docs-can't-lie tuned to fenced-only** (D-REGEX) — the naive whole-doc mirror *passes today*; fenced-only is
  preventive (breaks-proofs against gap-#9 prose) at the cost of not checking inline-prose references.
  Keep-recommended; the strict-mirror alternative is a legitimate choice. It also makes AGENTS.md
  **fence-parity-sensitive** (an odd number of triple-backtick runs mispairs the extractor), so it ships with two
  prose invariants and a parity guard — see D-REGEX (a)/(b).

## Acceptance

- `TMPDIR=<roomy> just ci` runs `… test policy audit` and ends `ci: all gates passed`; `just policy` alone passes
  in milliseconds.
- **Self-referential check — all five assertions pass on the *current* maintainer tree** (empirically proven in
  the design-review worktree: `uv run ruff check .` EXIT 0, `uv run basedpyright` "0 errors, 0 warnings",
  `uv run pytest tests/policy` → 5 passed): recommended ✓, failOnWarnings ✓, ALL ✓, every fenced `just <recipe>`
  real ✓, all 12 `uses:` SHA+`# v` pinned ✓.
- **That baseline predates the new AGENTS.md section and does *not* prove the post-edit state** — the section's
  first draft in fact **failed** it (D-REGEX (a)). The suite must be re-run **after** the AGENTS.md edit lands
  (plan Task 3 Step 7), preceded by a **fence-parity check**: AGENTS.md must hold an **even** number of
  triple-backtick runs — 16 today, **18** after the section is inserted (plan Task 3 Step 6).
- `just lint` + `just typecheck` clean on the new `tests/policy/*.py`.
- `just precommit` clean (new files end in `\n`; not `^template/`-excluded).
- Every `ci` gate-list site updated (D6 list). Verify with the **broadened** grep that catches the `+`-form:
  `grep -nE 'test ?\+? ?(policy ?\+? ?)?audit' justfile AGENTS.md` shows only `… policy … audit` forms, no stale
  `test audit` / `test + audit`.
- No `template/`, `test-template.yml`, `pyproject.toml` (deps), `mise.toml`, `uv.lock`, `tests/test_generation.py`,
  or CHANGELOG change.
- CI green (no workflow change; the existing `test` job collects `tests/policy`).

## Out of scope / tracked follow-up

- **Candidate F** (CI jobs call `just` recipes) — still deferred (gap #3 D5).
- **Property-tests (gap #9)** — will add `fuzz` to the `ci` list + this section (the forward-sync note's remaining
  obligation).
- **`_migrations`-required policy check** (roadmap Group F) — separate maintainer-side guard; not here.
- Dated `docs/superpowers/` snapshots — left frozen (pin-sync convention).

## Explicit no-touch (guard rails)

- No file under `template/`; no generation-test change (the layer's downstream assertions already exist).
- No `test-template.yml`, `pyproject.toml` deps, `mise.toml`, `uv.lock`, or CHANGELOG change.
- No inline `# noqa`; no Action SHA bump.
- No change to `scan`/`audit`/`test` recipe **bodies** (only `test`'s appearance in the `ci` list is unchanged;
  `test` body stays bare).

## Files touched (maintainer root only)

- `tests/policy/__init__.py` (new, empty)
- `tests/policy/test_gates.py` (new)
- `justfile` (add `policy`; `ci` gains `policy`; update `ci` comment)
- `AGENTS.md` (new Policy-gate section; sweep the `ci` gate-list sites + forward-sync note)
- `docs/superpowers/specs/2026-07-07-dogfood-policy-tests-design.md` +
  `docs/superpowers/plans/2026-07-07-dogfood-policy-tests.md` (this pair)
