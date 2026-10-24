# Kickstarter Workflow

A stdlib-only, POSIX helper for preparing isolated Python development, running real
checks, and returning only a reviewed product payload. It does not commit, publish,
upgrade a template, install hooks, or install agent skills.

## Develop

```bash
uv sync --locked
just ci
```

The unchanged generated gate includes Ruff ALL, recommended basedpyright,
unit tests with **85% branch coverage**, Hypothesis, policy tests, and the runtime
dependency audit. Runtime dependencies are empty; that audit is not a development
dependency audit. The locked development group includes Copier **9.15.2** and uv
**0.13.4**. Integration tests invoke those tools and require Git and just on PATH,
network access for task-local development environments, and a roomy `TMPDIR`.
No helper test installs hooks.

## Interface

```bash
uv run kickstarter-workflow --state "$HOME/.local/state/kickstarter-workflow" prepare plan.json
uv run kickstarter-workflow --state "$HOME/.local/state/kickstarter-workflow" verify plan.json
uv run kickstarter-workflow --state "$HOME/.local/state/kickstarter-workflow" return review.json
```

`python -m kickstarter_workflow` is equivalent. The Python interface is
`Workflow(Path(state_directory)).dispatch(operation, request_dict)`. It returns the
same JSON-compatible object as the CLI. Operations are `prepare`, `resume`,
`status`, `verify`, `return`, and `cleanup`. A completed operation has status
`prepared`, `exempt`, `verified`, `returned`, or `cleaned` and CLI exit zero.
`blocked`, `preparing`, `verifying`, `review_required`, and `returning` are **not**
completed delivery; the CLI exits 2. `review_required` retains a verified reconciled
candidate but requires receipt-bound host review before any transfer. Missing state
is a blocker, never a fresh implicit task. Invoke concurrent tasks
in separate processes; the Python interface is not a thread-safe process launcher.

Preparation is not verification. Workbench verification is not destination
validation. The result includes the workspace, retained plan, actual tool identities,
and, after verification, receipt identity and measured product tests/coverage.
Diagnostics are local metadata containing absolute paths, not a portable identity
or a shareable report. Keep the durable state directory outside source repositories
and outside scratch/cache expiry policies. It must be owned by the caller, mode 0700.

### Plan

All mappings are explicit **files**, not directory globs. Include runtime code,
maintained tests, imported local dependencies, fixtures, assets and relevant context.
Explicit declarations remain inventoried even when their names resemble generated reports
or caches (for example, `fixtures/coverage.json`). Git/environment control paths,
links and special files remain forbidden. The full original tree is separately
inventoried and copied for repository checks.
The scope review is a human-reviewed declaration, not proof of adequate coverage.
An omitted dependency, meaningless assertion, or missing CI obligation remains a
review finding even when mechanically selected checks pass.

```json
{
  "project": "sample",
  "task": "fix-double",
  "mode": "workbench",
  "source": "/absolute/product-repository",
  "template": {
    "source": "https://github.com/maybebyte/python-kickstarter.git",
    "revision": "37adbeeea53a242ed25db602a35b9d719d95c8ae",
    "cache": "/absolute/clean-detached-template-cache"
  },
  "tools": {
    "git": "/absolute/bin/git",
    "copier": "/absolute/bin/copier",
    "uv": "/absolute/bin/uv",
    "just": "/absolute/bin/just"
  },
  "answers": {
    "project_name": "Sample",
    "package_name": "sample",
    "author_name": "The project maintainer",
    "author_email": "maintainer@example.invalid",
    "description": "The established product purpose.",
    "license": "ISC",
    "python_version": "3.11",
    "project_type": "library"
  },
  "mapping": [
    {"source": "app.py", "target": "product/app.py", "role": "source"},
    {"source": "test_app.py", "target": "product/test_app.py", "role": "test"},
    {"source": "README.md", "target": "product/README.md", "role": "context"}
  ],
  "repository_checks": [
    ["uv", "run", "--project", "{workspace}", "pytest", "--override-ini=addopts=", "test_app.py"]
  ],
  "scope_review": "Complete product slice and all repository obligations reviewed."
}
```

Resolve identity, license, Python compatibility and application/library choices from
project evidence. Do not copy personal identity into work projects or select template
answers that downgrade a product contract. The helper requires explicit answers and
lets Copier validate supported values. Tool paths can be discovered with the Python
`kickstarter_workflow.process.default_tools()` utility; discovery installs nothing.

The cache must be a clean, detached canonical Git clone at the exact reviewed commit.
Moving branches, tags alone, dirty files, noncanonical remotes, symlink paths and
unapproved revisions are refused. This initial release approves only the commit above;
adding another reviewed revision is a helper policy change, not an automatic update.
The source cache is never mutated by the helper. Copier renders with `--skip-tasks`;
Git initialization is explicitly scoped with an empty template and disabled hooks.
A generated answers file is preserved byte-for-byte. Copier may record a Git describe
value there; the separate task record contains the resolved full approved commit.

Preparation creates and locks the task-local environment before reporting readiness.
Resume and repeated preparation validate the retained source/scaffold inventories,
baseline, exact Git roots, environment, tool/template identities and frozen gate
configuration. Missing or changed setup evidence blocks readiness while preserving
the workspace; ordinary product edits remain resumable.

Modes:

- **`workbench`**: existing, non-Kickstarter repository. Generate under the private
  task directory. Targets must start with `product/`. The helper adapts the generated
  gate's targets and existing test-only lint exceptions to those files. It does not
  copy its scaffold back to the product.
- **`existing`**: existing Kickstarter repository. Copy its complete relevant tree
  into an isolated task repository; validate and preserve its answers/configuration.
  Use identical source/target mappings. No regeneration or upgrade occurs. The
  documented `gh:maybebyte/python-kickstarter` origin is accepted alongside the
  canonical HTTPS origin and the validated local cache path; the cache must still
  be canonical and the recorded revision must resolve to the exact approved commit.
- **`new`**: generate at the explicitly authorized, nonexistent `source` destination.
  Use identical source/target mappings. Set `isolate_git: true` only when explicitly
  authorizing a new independent Git root beneath an existing ancestor. Unchanged
  generated example tests cannot establish product verification. This mode already
  occupies its destination and has no copy-back operation.
- **`disposable`**: only `project`, `task`, `mode` and a nonempty `reason` are needed.
  The exemption is durable but cannot verify or return production work. Re-enter
  `prepare` with a production plan to promote it; the exemption history is retained.

Use `new: true` on a mapping to declare a **new** maintained source/test/context file
before writing it in the workbench. An existing source at that path is refused.
All declared source/test targets must exist before verification. Ordinary file
replacement/addition is supported; file deletion, symlink payloads, special files,
hardlinked payloads and scaffold adoption are deliberately refused.

Mapped test paths preserve spaces, BMP Unicode and literal shell punctuation through
the generated recipe. Test mappings containing `{`, `}`, `[`, `]`, `*`, `?`, or
`::` are refused before tool execution: just interpolation, Ruff glob patterns and
pytest selectors are not literal filename transport. Shell quoting alone cannot
neutralize those parsers. A mapped `product/__init__.py` is never replaced with
helper scaffolding; a declared new initializer remains absent until authored.
Non-BMP Unicode test paths currently fail during setup and are not supported.

A source must be the exact declared Git root. Nested generated subprojects and
repository migration need an explicitly arranged isolated repository-root layout;
this helper will not silently widen a scan to an enclosing repository or home.

### Existing product dependencies and packaging

For a workbench source with `pyproject.toml`, declare its environment before
preparation and map that file to `product/pyproject.toml` as context:

```json
{
  "environment": {
    "project": "pyproject.toml",
    "groups": [],
    "extras": []
  }
}
```

Select only groups/extras required by the declared product slice. The helper reads
the existing static PEP 621 dependencies and Python compatibility, adding the
dependencies to workbench development setup without changing the product's runtime
declarations. Selected groups and extras must contain flat dependency lists.

Local packaged products currently require the default `uv_build` layout and a
complete layout-preserving mapping: every relevant source, test, metadata file and
asset maps to `product/<original-path>`. The workbench installs that local package
editable with its declared build requirements. Destination checks import from the
destination layout rather than silently continuing to test the workbench copy.

Dynamic metadata, custom `tool.uv` configuration, other build backends and legacy
requirements/setup formats block preparation. The helper reports these limits
rather than guessing dependency or packaging behavior. A dependency-free script
without project metadata needs no environment declaration. Installing existing
declared dependencies in the isolated environment does not authorize changing them
in the product.

### Check plan and evidence

The helper always executes generated `just ci`, a separate measured product test
run, and the declared repository checks in an isolated complete repository snapshot.
A repository `justfile` adds mandatory `just ci` even if omitted from the list.
An existing `.kickstarter-checks.json` containing `{"checks": [["just", "ci"]]}`
adds repository-owned commands; this helper never creates that file in a product.
Declare remaining mandatory CI commands and changed-risk extras in
`repository_checks` **before editing**, including any development audit, SAST or
mutation work required by review. Commands are argument arrays, not shell strings;
the executable must be in the explicit toolbox. `{workspace}` in declared command
arguments selects the generated development environment without changing the
repository check's working directory.

Before isolated checks, the helper builds a disposable discovery index from every
inventoried candidate file, including untracked and ignored product files. Blobs
use literal bytes without Git filters. This index deliberately represents the
whole candidate, not the source's staged/unstaged distinction. The source index,
local configuration and hooks are never copied for execution; original Git state
is not rewritten. Local reachable history and exact refs/HEAD are retained in a content-bound Git
bundle and restored independently for repository copies and reused projects.
Unborn repositories honestly retain no commits; the helper does not manufacture
history. Receipts bind semantic indexes and refs, and repository checks that change
their measured files or Git inputs are refused. Changed source refs or damaged
retained bundles invalidate readiness and require a new task or explicit recovery.

The reviewed check plan may specify `git_requirements`, defaulting to
`["index", "history", "refs"]`, which is also the supported set. Requirements for
reflogs, source staging state, local configuration, remote access or other Git
semantics must be declared and are blocked, not emulated. Shallow/partial clones,
grafts and replacement objects are unsupported. This covers complete **locally
reachable** history, not unreachable objects or unfetched remote history. Reviewers
must assess executable checks against this boundary; the helper cannot infer
arbitrary scripts' unstated requirements. Destination checks retain the actual
destination Git context without rewriting its index.

Prepared template gate configuration, lockfile and policy tests are frozen: changing
their bodies, thresholds or configuration requires a newly reviewed preparation,
not a success marker. Existing generated projects retain their actual enabled gates
and approved thresholds, including legitimately disabled optional gates. New
workbenches retain the strict defaults. The helper does not waive required failures.
Subsequent environment sync uses the lock. Lock/sync and developer
downloads stay within task workspaces/designated caches; no runtime dependency
change is authorized by this workflow.

Every tool invocation has a pre-execution `running` record, exact argv/cwd, raw merged
stdout/stderr and final exit status. A verification receipt binds all relevant
candidate bytes **and modes**, the plan, uv lockfile and actual executable identities;
it fingerprints the raw command records, JUnit results and branch coverage JSON.
The separate product run must discover successful maintained tests and execute every
mapped source file at the approved coverage threshold: at least 85% for new
workbenches, or the existing generated project's preserved floor. Missing, empty, failed, interrupted,
modified or stale evidence does not authorize return. Restoring identical verified
inputs can reuse the unchanged receipt; a failed new verification supersedes it.

Repository checks and product tests are executable project code. This is a workflow
control for reviewed code, **not a sandbox against a hostile same-user process** or
an untrusted repository. Private records prevent accidental shared mutable task
state; a process with the same filesystem privileges can still deliberately tamper
with code/state or bypass the workflow. Independent code/configuration review is
required to judge gate adequacy and execution authority.

### Reviewed return

```json
{
  "project": "sample",
  "task": "fix-double",
  "review": {
    "receipt": "the exact receipt returned by verify",
    "reviewer": "independent review reference",
    "reason": "Reviewed product delta and complete maintained regressions.",
    "allowlist": ["app.py", "test_app.py"]
  }
}
```

The allowlist uses **source/destination** names, must contain every changed mapped
file, and cannot introduce unmapped payloads. Generated configuration, locks, hooks,
CI and reports do not travel by default; this release refuses their adoption rather
than inventing authorization. Review is an explicit caller attestation bound to a
receipt, not proof that an independent reviewer really performed the review.

Destination drift is compared with the retained source snapshot. Textually compatible
three-way changes refresh the snapshot and rerun gates. When that changes candidate
bytes or modes, `return` stops before transfer with `status: "review_required"`, a new
`receipt`, `previous_receipt`, and `reconciliation_diff`. The host's independent
reviewer must inspect the new candidate's behavioral intent and submit an updated
review bound to the new receipt. The old review is rejected. This review can proceed
within existing task authority for compatible intent; behavioral conflicts or unclear
ownership require a user decision. Textual merging and coverage alone do not prove
semantic compatibility. Unchanged-candidate drift can proceed without another review.

Content, add/delete or incompatible mode conflicts block with work retained.
Unrelated newer destination files are preserved. All required repository checks and
measured product tests rerun in the destination layout after transfer. The helper
then checks that the reviewed payload, unrelated destination files, workspace inputs
and bound evidence remain unchanged. A check that rewrites a file cannot turn that
changed candidate into an accepted delivery. Publication remains the host's separate
authority.

Transfers journal the intended before/after states before the first replacement.
`status` reports actual effects after interruption, even if a replacement happened
before its journal update. Retry with the **same** review skips files already applied,
refuses unexpected newer content and reruns destination checks. It never blindly
replays the writes. File writes and immediate-parent entries are fsynced; this is not
a multi-file filesystem transaction or a power-loss guarantee. Cooperating process
ownership and immediately repeated destination checks do not provide atomic CAS
against arbitrary simultaneous external writers.

On failed destination validation, `transferred` records files matching the payload
before checks, while `applied` reports those still matching afterward.
`destination_changes` identifies changes made during the checks, and
`destination_validated` remains false. Inspect the retained journal and actual
effects before recovery; a failed check is not a rollback.

`cleanup` is explicit, only for returned/exempt/resolved work. It removes the owned
workspace, never a source project, and retains records/raw evidence. Unresolved
work, malformed/partial records and pending atomic writes require a decision and
are preserved. There is no cleanup daemon.

Task ownership remains independent. Only shared project-metadata inspection and
publication use a short project-level lock; competing publishers wait rather than
mistaking an active write for abandoned recovery state. A pending write left after
the publisher exits blocks readiness and cleanup until explicitly reconciled.

## Evidence and platform scope

Tests preserve literal examples, real Copier/Git integration, path/receipt/lifecycle
Hypothesis properties, failed-gate cases, compatible/conflicting drift, and a real
SIGINT-at-replacement child-process recovery case. Recorded repair verification
includes the full helper gate on Linux/Python 3.14.6 and focused regressions on
Python 3.11.15. These results do not establish arbitrary crash timing, hostile
concurrent writers, Windows support or live native agent discovery. Native
Hermes/Claude/Codex routing and installation are separate rollout work.
