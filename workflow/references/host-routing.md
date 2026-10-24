# Route host entrypoints to the shared workflow

This is rollout guidance, not an installer. Keeping these files in the Kickstarter repository does not activate them in Hermes, Claude Code or Codex. A code-only implementation assignment leaves installed skills unchanged.

## Before an authorized rollout

1. Resolve the active host profile, actual skill paths, symlinks/bind mounts and managed plugin ownership. Inventory all consumers of shared files before changing them. Preserve unrelated profiles and managed plugin caches.
2. Read the installed implementation and review contracts. Keep their authority rules intact: a host that requires permission before committing must still require it; a host that authorizes an assigned task through a PR must not gain new routine approval stops.
3. Select one reviewed checkout/version of this repository as the shared source. Keep `workflow/` and `automation/` together, or supply an explicit verified helper location when packaging them. Copying only `SKILL.md` breaks its relative references.
4. Adapt the small insertion points below into the existing entrypoints. Do not replace whole skills or copy the workflow body into several competing sources. Review and test the complete installed candidate, including references.

## Implementation insertion point

Place the requirement where the host decides its development workspace, before production edits. Replace `WORKFLOW_PATH` with the authorized installation's resolved path during rollout, not with a machine-specific path in this repository.

> For maintained or shipped Python, read `WORKFLOW_PATH/SKILL.md` and prepare the real product workspace through its helper before editing. Use an external workbench for an existing untemplated repository unless permanent adoption is authorized. Disposable one-off scripts remain exempt until promoted. Verify the exact candidate before delivery and report the helper receipt, tested product scope and destination validation. This routing preserves this host's existing implementation authority, test-first standard, independent review and delivery endpoint. Pass the same workflow and evidence requirements to delegated implementers and reviewers.

## Reviewer insertion point

Place the requirement beside the host's requirements and standards review packet.

> For maintained or shipped Python, read `WORKFLOW_PATH/SKILL.md` and assess preparation, actual product execution, candidate-bound receipts and authorized return against its reviewer checklist. Reject missing/stale evidence, scaffold-only success and omitted mandatory checks. Assess the test/property disposition from evidence rather than inheriting the implementer's verdict. A helper pass does not replace independent code/configuration review or prove native skill discovery.

## Verify the rollout separately

Exercise fresh native implementation and reviewer sessions for every supported host and affected shared consumer. Use ordinary task entrypoints without supplying the workflow name, path or expected answer in the task prompt. Inspect actual reads, helper calls and refused inadequate results; an agent promising to use the workflow is not discovery evidence.

Use disposable cases for maintained Python in an untemplated repository, a justified disposable-script exemption, missing preparation/provenance and a proposed stale or scaffold-only result. Keep each probe's write/publication boundaries explicit. Explicitly loading this skill tests its instructions, not spontaneous routing.

Record separately:

- Files installed and the exact version/bytes they contain.
- Native loader discovery of the intended source, with duplicate identities resolved.
- Observed ordinary-task selection and helper behavior for implementation and review.
- Excluded profiles/accounts and untested platforms or consumers.

A failed discovery test leaves the installation unverified. Preserve the host's earlier contract and recoverable candidate; do not enable hooks, alter managed caches or broaden permissions to force a pass.
