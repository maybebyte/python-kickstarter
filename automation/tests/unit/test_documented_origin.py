"""Reuse real Copier output from the documented GitHub abbreviation, offline."""

import os
import re
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow
from tests.conftest import CANONICAL, PIN, command


def test_documented_origin_is_reused_without_broadening_provenance(
    tmp_path: Path, plan: Record, template_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "generated"
    answers = object_value(plan, "answers")
    arguments = [
        "copier",
        "copy",
        "--defaults",
        "--skip-tasks",
        "--vcs-ref",
        PIN,
        "--data",
        "enable_precommit_install=false",
    ]
    for key in answers:
        arguments.extend(["--data", key + "=" + text(answers, key)])
    # Only Git transport is redirected; Copier receives the documented origin.
    with monkeypatch.context() as transport:
        count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
        transport.setenv("GIT_CONFIG_COUNT", str(count + 1))
        transport.setenv(f"GIT_CONFIG_KEY_{count}", "url." + template_cache.as_uri() + ".insteadOf")
        transport.setenv(f"GIT_CONFIG_VALUE_{count}", CANONICAL)
        transport.setenv("GIT_ALLOW_PROTOCOL", "file")
        command(*arguments, "gh:maybebyte/python-kickstarter", str(source), cwd=tmp_path)
    command("git", "init", "--quiet", "--template=", str(source), cwd=tmp_path)
    request: Record = {
        **plan,
        "mode": "existing",
        "source": str(source),
        "mapping": [
            {
                "source": "src/sample/__init__.py",
                "target": "src/sample/__init__.py",
                "role": "source",
            },
            {
                "source": "tests/unit/test_example.py",
                "target": "tests/unit/test_example.py",
                "role": "test",
            },
        ],
        "repository_checks": [["just", "ci"]],
    }
    answer_file = source / ".copier-answers.yml"
    original = answer_file.read_bytes()
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    assert prepared["template_revision"] == PIN
    assert answer_file.read_bytes() == original
    assert (workspace / ".copier-answers.yml").read_bytes() == original
    for name in ("pyproject.toml", "justfile"):
        assert (workspace / name).read_bytes() == (source / name).read_bytes()
    assert workflow.dispatch("resume", request)["status"] == "prepared"
    invalid = (
        ("_src_path", "gh:someone-else/python-kickstarter"),
        ("_src_path", "gh:maybebyte/python-kickstarter.git"),
        ("_commit", "v0.2.0"),
    )
    for index, (key, value) in enumerate(invalid):
        changed = re.sub(
            r"^" + key + r": .+$", key + ": " + value, original.decode(), flags=re.MULTILINE
        )
        assert changed.encode() != original
        _ = answer_file.write_text(changed)
        task = "invalid-" + str(index)
        refused = workflow.dispatch("prepare", {**request, "task": task})
        assert refused["status"] == "blocked", refused
        assert answer_file.read_text() == changed
        assert not (tmp_path / "state/sample" / task / "workspace").exists()
    _ = answer_file.write_bytes(original)
    assert workflow.dispatch("resume", request)["status"] == "prepared"
