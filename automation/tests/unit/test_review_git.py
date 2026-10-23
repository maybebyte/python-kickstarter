"""Repository checks must measure the candidate, not an empty Git index."""

from pathlib import Path

import pytest

from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import Record, load, object_value, text
from kickstarter_workflow.workflow import Workflow


@pytest.mark.parametrize("document", ["README.md", " leading.md"])
def test_repository_owned_git_gate_rejects_the_actual_candidate(
    tmp_path: Path, plan: Record, document: str
) -> None:
    source = Path(text(plan, "source"))
    if document != "README.md":
        _ = (source / "README.md").rename(source / document)
        mapping = plan["mapping"]
        assert isinstance(mapping, list)
        assert isinstance(mapping[2], dict)
        mapping[2]["source"] = document
    _ = (source / "justfile").write_text(
        "ci:\n    ! git grep -n FORBIDDEN_REVIEW_MARKER -- '*.md'\n"
    )
    runner = Runner(object_value(plan, "tools"), tmp_path / "setup", tmp_path / "cache")
    _ = runner.run(["git", "add", "app.py", "test_app.py", "justfile"], source)
    index = (source / ".git/index").read_bytes()
    config = (source / ".git/config").read_bytes()
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    _ = (workspace / "product/README.md").write_text("FORBIDDEN_REVIEW_MARKER\n")
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked", result
    records = [load(p) for p in (tmp_path / "state/sample/one").glob("run-*/*.json")]
    failed = [
        r
        for r in records
        if r.get("exit") == 1
        and "/repository-" in str(r.get("cwd"))
        and r.get("argv") == [text(object_value(plan, "tools"), "just"), "ci"]
    ]
    assert len(failed) == 1, records
    assert f"{document}:1:FORBIDDEN_REVIEW_MARKER" in Path(text(failed[0], "output")).read_text()
    assert (source / ".git/index").read_bytes() == index
    assert (source / ".git/config").read_bytes() == config
    assert (source / document).read_text() == "Product contract: double the input.\n"


def test_repository_history_and_refs_survive_without_source_git_changes(
    tmp_path: Path, plan: Record, template_cache: Path
) -> None:
    source = Path(text(plan, "source"))
    runner = Runner(object_value(plan, "tools"), tmp_path / "setup", tmp_path / "cache")
    pin = text(object_value(plan, "template"), "revision")
    _ = runner.run(["git", "fetch", "--no-tags", str(template_cache), pin], source)
    _ = runner.run(["git", "update-ref", "refs/heads/review-base", pin], source)
    _ = runner.run(["git", "symbolic-ref", "HEAD", "refs/heads/review-base"], source)
    _ = (source / "justfile").write_text(
        "\n".join(
            [
                "ci:",
                "    git cat-file -e HEAD:copier.yml",
                f'    test "$(git rev-parse refs/heads/review-base)" = {pin}',
                "    git ls-files --error-unmatch README.md",
                "",
            ]
        )
    )
    _ = runner.run(["git", "add", "app.py"], source)
    before = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in (source / ".git").rglob("*")
        if p.is_file()
    }
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    after = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in (source / ".git").rglob("*")
        if p.is_file()
    }
    assert after == before
    assert workflow.dispatch("status", plan)["status"] == "verified"
    _ = runner.run(["git", "update-ref", "refs/heads/changed", pin], source)
    assert workflow.dispatch("status", plan)["status"] == "blocked"
    _ = runner.run(["git", "update-ref", "-d", "refs/heads/changed"], source)
    assert workflow.dispatch("status", plan)["status"] == "verified"
    workspace = Path(text(prepared, "workspace"))
    _ = runner.run(["git", "update-index", "--force-remove", "product/app.py"], workspace)
    assert workflow.dispatch("status", plan)["status"] == "blocked"


def test_unsupported_git_requirements_are_blocked_before_generation(
    tmp_path: Path, plan: Record
) -> None:
    plan["git_requirements"] = ["reflogs"]
    result = Workflow(tmp_path / "state").dispatch("prepare", plan)
    assert result["status"] == "blocked", result
    assert not (tmp_path / "state/sample/one/workspace").exists()


def test_repository_check_cannot_change_the_measured_git_index(
    tmp_path: Path, plan: Record
) -> None:
    source = Path(text(plan, "source"))
    _ = (source / "justfile").write_text("ci:\n    git update-index --force-remove README.md\n")
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked", result
    records = [load(p) for p in (tmp_path / "state/sample/one").glob("run-*/*.json")]
    assert any(
        r.get("exit") == 0
        and "/repository-" in str(r.get("cwd"))
        and r.get("argv") == [text(object_value(plan, "tools"), "just"), "ci"]
        for r in records
    )


@pytest.mark.parametrize("context", ["shallow", "grafts", "replacement"])
def test_incomplete_or_rewritten_history_cannot_provide_readiness(
    tmp_path: Path, plan: Record, template_cache: Path, context: str
) -> None:
    source = Path(text(plan, "source"))
    runner = Runner(object_value(plan, "tools"), tmp_path / "setup", tmp_path / "cache")
    pin = text(object_value(plan, "template"), "revision")
    depth = ["--depth=1"] if context == "shallow" else []
    _ = runner.run(["git", "fetch", "--no-tags", *depth, str(template_cache), pin], source)
    _ = runner.run(["git", "update-ref", "HEAD", pin], source)
    if context == "grafts":
        (source / ".git/info").mkdir(exist_ok=True)
        _ = (source / ".git/info/grafts").write_text(pin + "\n")
    elif context == "replacement":
        _ = runner.run(["git", "update-ref", "refs/replace/" + pin, pin], source)
    result = Workflow(tmp_path / "state").dispatch("prepare", plan)
    assert result["status"] == "blocked", result


def test_reused_project_gate_sees_untracked_candidate_files(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    new: Record = {
        **plan,
        "mode": "new",
        "source": str(tmp_path / "new-project"),
        "isolate_git": True,
    }
    new["mapping"] = [
        {"source": "src/sample/__init__.py", "target": "src/sample/__init__.py", "role": "source"},
        {
            "source": "tests/unit/test_example.py",
            "target": "tests/unit/test_example.py",
            "role": "test",
        },
    ]
    new["repository_checks"] = [["just", "ci"]]
    generated = workflow.dispatch("prepare", new)
    assert generated["status"] == "prepared", generated
    source = Path(text(new, "source"))
    gate = source / "justfile"
    _ = gate.write_text(
        gate.read_text().replace(
            '    @echo "ci: all gates passed"',
            "    ! git grep -n FORBIDDEN_REVIEW_MARKER -- '*.md'",
        )
    )
    _ = (source / "README.md").write_text("FORBIDDEN_REVIEW_MARKER\n")
    reuse: Record = {**new, "mode": "existing", "task": "reuse"}
    prepared = workflow.dispatch("prepare", reuse)
    assert prepared["status"] == "prepared", prepared
    result = workflow.dispatch("verify", reuse)
    assert result["status"] == "blocked", result
    records = [load(p) for p in (tmp_path / "state/sample/reuse").glob("run-*/*.json")]
    failed = [
        r
        for r in records
        if r.get("exit") == 1 and r.get("argv") == [text(object_value(plan, "tools"), "just"), "ci"]
    ]
    assert len(failed) == 1, records
    assert "README.md:1:FORBIDDEN_REVIEW_MARKER" in Path(text(failed[0], "output")).read_text()
    assert not (source / ".git/index").exists()
