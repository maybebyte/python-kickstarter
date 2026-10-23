"""Reuse the actual generated gates and threshold, without weakening them."""

from pathlib import Path

from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow
from tests.conftest import PIN, command


def test_existing_optional_gates_and_approved_coverage_are_preserved(
    tmp_path: Path, plan: Record, template_cache: Path
) -> None:
    source = tmp_path / "existing"
    answers = [
        arg
        for key, value in object_value(plan, "answers").items()
        for arg in ("--data", f"{key}={value}")
    ]
    command(
        "copier",
        "copy",
        "--defaults",
        "--skip-tasks",
        "--vcs-ref",
        PIN,
        *answers,
        "--data",
        "enable_precommit_install=false",
        "--data",
        "enable_property_tests=false",
        "--data",
        "enable_dependency_audit=false",
        "--data",
        "coverage_floor=60",
        "--data",
        "package_name=sample",
        "--data",
        "ruff_ruleset=curated",
        str(template_cache),
        str(source),
        cwd=tmp_path,
    )
    command("git", "-c", "init.templateDir=", "init", "--quiet", str(source), cwd=tmp_path)
    (source / "src/sample/core.py").unlink()
    _ = (source / "src/sample/__init__.py").write_text(
        '"""Existing product."""\n\n\ndef twice(value: int) -> int:\n    """Double the magnitude."""\n    if value < 0:\n        return -value * 2\n    return value * 2\n'
    )
    _ = (source / "tests/unit/test_example.py").write_text(
        '"""Established partial coverage."""\n\nfrom sample import twice\n\n\ndef test_twice() -> None:\n    assert twice(3) == 6\n'
    )
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
    original = (source / "pyproject.toml").read_bytes()
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    assert (workspace / "pyproject.toml").read_bytes() == original
    verified = workflow.dispatch("verify", request)
    assert verified["status"] == "verified", verified
    assert 60 <= int(str(verified["product_coverage"])) < 85
    config = workspace / "pyproject.toml"
    _ = config.write_text(config.read_text().replace("fail_under = 60", "fail_under = 1"))
    assert workflow.dispatch("verify", request)["status"] == "blocked"
    assert object_value(request, "template")["revision"] == PIN
    assert (source / "pyproject.toml").read_bytes() == original
