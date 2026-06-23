# python-kickstarter

A [Copier](https://copier.readthedocs.io/) template that scaffolds a fully-gated Python project — pre-commit hooks, ruff, basedpyright, pytest with branch coverage, optional property/mutation/policy tests, optional scanners and dependency audit, and a `just ci` gate that is green from the first commit.

## Use

```bash
copier copy --trust gh:OWNER/python-kickstarter ./myproj
```

`--trust` is required on both copy and update because the template uses Copier's `_tasks` and `_migrations` features, which Copier classifies as "unsafe".

To update a downstream project after a new template release:

```bash
copier update --trust
```

## Toggles

All toggles default to `true` — every guardrail layer ships unless you opt out.

| Toggle | What it enables |
|---|---|
| `enable_property_tests` | Hypothesis property suite (`just fuzz`) |
| `enable_mutation_tests` | mutmut mutation suite (`just mutate`) |
| `enable_policy_tests` | stdlib policy assertions (`just policy`) |
| `enable_scanners` | Semgrep + gitleaks scan recipe (`just scan`) |
| `enable_dependency_audit` | pip-audit recipe (`just audit`) |
| `enable_renovate` | Renovate bot config |
| `enable_sha_pin_policy` | zizmor workflow audit in CI, plus a CI policy test asserting all Action SHAs are pinned — the policy test requires `enable_policy_tests` (only the zizmor audit ships otherwise) |

Beyond their `just` recipes, several toggles also emit GitHub Actions workflows: `enable_scanners`, `enable_dependency_audit`, and `enable_sha_pin_policy` each contribute steps to a generated `scan.yml` (semgrep + gitleaks, pip-audit, and zizmor respectively), and `enable_mutation_tests` emits a scheduled `mutation.yml`. The always-on `ci.yml` runs the `just ci` gate across a Python-version matrix.

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- [just](https://just.systems/)
- [Copier](https://copier.readthedocs.io/) ≥ 9.6

## Maintainers

See `AGENTS.md` for the template extension contract (adding guardrail layers, releasing, CI pinning rules).
