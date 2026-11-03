---
name: python-kickstarter-workflow
description: Prepare and verify maintained Python changes with Copier.
compatibility: Python 3.11+, Git, Copier, uv and just on Linux or macOS.
metadata:
  version: 0.1.0
  author: Ashlen (maybebyte), Hermes Agent
  license: ISC
---

# Python Kickstarter workflow

Use this procedure before editing maintained or shipped Python, and when reviewing its delivery evidence. It supplements the host's implementation contract; that contract still determines edit, commit, publication and installation authority. Disposable one-off scripts are exempt until they become maintained or shipped.

The deterministic helper lives in [`../automation/`](../automation/README.md). Read its current interface reference before invoking it with the host's terminal tool. Resolve linked paths relative to this file, not the product's working directory. Installation and normal-entrypoint routing are separate work: see [host routing](references/host-routing.md) only when that work is authorized.

## Prepare before production edits

1. Recover the product's behavior, source root, identity, license, Python compatibility and application/library role from its repository. Record the task's authority and declare the real product slice, including its tests, fixtures, dependencies and packaging context. Ask only when consequential intent cannot be recovered. Finish when every required input has evidence or a specific blocker.
2. Select the workspace branch: generate a new project's authorized destination; reuse an existing generated project's configuration in an isolated task checkout; otherwise generate an external workbench. Permanent adoption in an existing repository needs separate authority. Resume only validated same-task state; different tasks require separate mutable workspaces. Finish when ownership and source/test mappings are recorded.
3. Select a reviewed exact template commit and record the canonical source, resolved revision and tool identities. Review executable template features before use. Skip generation tasks and perform controlled environment setup; validate Git ancestry independently so a home-wide ancestor cannot become the scan root. Preserve the generated answers file. Existing projects keep their pinned template revision. Finish when the helper reports preparation complete, not merely when a directory exists.

Setup permission covers task-local development dependencies, lock/sync and environments. Installing, activating or modifying hooks requires separate authorization, including in generated projects. Global installs, spending, changed runtime dependencies, template upgrades and live skill rollout are separate decisions. Read-only diagnosis can continue while setup is blocked.

## Develop and verify the actual product

1. Preserve generated template CI and every mandatory repository gate. Choose additional scanners, developer-dependency auditing and mutation diagnostics from the changed risk before editing. Keep thresholds and established exceptions. If required gates need broader repairs, present that concrete scope decision rather than weakening the gate.
2. Develop through the host's test-first contract. Test public behavior, retain new regressions in the maintained product suite, and assess meaningful generated-input properties where supported. Adapt measurement paths to the real product rather than accepting scaffold-only tests or empty scans. Finish each slice with observed regression sensitivity and passing affected checks.
3. Invoke the helper's verification operation. It owns command execution and receipts; an agent-written success marker is not evidence. Check actual product test execution, coverage targets, tool/configuration identities and candidate bytes/modes. Reject missing, failed, interrupted or stale required results. Distinguish an empty runtime audit from an audit of developer tools.
4. Obtain independent review of both the candidate and the selected gate plan. Supply the complete staged/unstaged/new-file candidate, source identity, requirements, test/property disposition and raw receipts. Reviewers must challenge inadequate measurement and omitted mandatory checks rather than accepting a green summary.

**Verification complete:** required checks pass or have an explicitly approved scoped exception, the evidence still matches the reviewed candidate, and reviewers have no unresolved blocking findings. A workbench pass does not establish destination validity.

## Return and deliver

1. Build the reviewed product-file allowlist. Keep generated scaffolding, lockfiles, hooks, CI and reports out unless their adoption is authorized. Verify the source stayed unchanged by workbench development and compare destination state immediately before transfer.
2. Use the helper's authorized return operation within the host assignment's scope. Compatible destination drift requires a refreshed snapshot, intent-preserving reconciliation and rerun checks. If reconciliation changes candidate bytes or modes, have the host's independent reviewer assess the new candidate and bind approval to its new receipt before transfer. Textual merge success and coverage do not establish preserved intent. This review can proceed automatically for compatible changes; behavioral conflicts or unclear ownership require a user decision. Never use an old receipt to overwrite newer files.
3. Rerun required destination-layout checks. Report verification, transferred files and destination validation separately. On interruption, retain diagnostics and inspect actual partial effects before resuming; do not blindly repeat writes or describe an uncertain outcome as success.
4. Follow the host's authorized delivery endpoint. Keep a compact external project record with validated mappings, template/tool identities, rerun instructions and the latest accepted receipt. Retain unresolved workspaces. Cleanup is explicit; durable records must survive scratch expiry.

**Delivery complete:** the exact reviewed payload reaches the authorized endpoint, required destination checks support it, and remaining human gates and untested scope are stated. This workflow neither grants merge/deployment permission nor makes tool-level bypass impossible.

## Reviewer checklist

- Does preparation select the right project branch without an implicit migration, update or hook installation?
- Do tests and scanners exercise the declared real product slice, with unchanged mandatory gates and an evidence-backed property disposition?
- Do receipts bind the final candidate, relevant tests/configuration, tooling and measured paths rather than a prior version?
- Does the reviewed allowlist preserve newer/unrelated destination files, with fresh evidence after reconciliation and honest partial-transfer reporting?
- Are code readiness, installation and observed fresh-native-agent discovery reported separately?
