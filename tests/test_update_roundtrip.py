"""REQUIRED: exercise `copier update`'s 3-way merge across a real version delta."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import copier
import pytest

from tests.test_generation import FULL, MINIMAL

if TYPE_CHECKING:
    from pathlib import Path

DATA = {**MINIMAL, "enable_precommit_install": False}


def _git(repo: Path, *args: str) -> None:
    # commit.gpgsign=false / tag.*sign=false: a global `commit.gpgsign=true` or
    # `tag.forceSignAnnotated=true` would otherwise make these commits/tags hang
    # or fail in a signing-configured environment (the maintainer's, and CI's).
    _ = subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "tag.forceSignAnnotated=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "answers",
    [
        pytest.param(MINIMAL, id="minimal"),
        pytest.param(FULL, id="full"),
    ],
)
def test_update_across_versions_has_no_conflicts(
    template_root: Path, tmp_path: Path, answers: dict[str, object]
) -> None:
    """The 3-way merge stays clean across a version delta — bare tree AND fully-layered.

    The minimal tree never exercises conditional/empty-name files, so a change that breaks
    `copier update` only for layered projects would slip through. The v0.2.0 delta below
    also edits a scanners-only file, so the merge crosses a guardrail surface when the
    layers are on.
    """
    data = {**answers, "enable_precommit_install": False}

    # Work on a throwaway copy so the real template repo is never mutated.
    tpl = tmp_path / "template-copy"
    _ = shutil.copytree(
        template_root,
        tpl,
        ignore=shutil.ignore_patterns(".git", ".venv", "dist", ".pytest_cache", "__pycache__"),
    )
    _git(tpl, "init")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.1.0")
    _git(tpl, "tag", "v0.1.0")

    # Generate a downstream project from the OLD tag and commit it.
    dst = tmp_path / "downstream"
    _ = copier.run_copy(
        str(tpl),
        str(dst),
        data=data,
        defaults=True,
        unsafe=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v0.1.0",
    )
    _git(dst, "init")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "init from v0.1.0")

    # v0.2.0 template change: an always-present file (README) plus a scanners-only file,
    # so a layered update merges a conditional guardrail surface, not just the README.
    readme = tpl / "template" / "README.md.jinja"
    _ = readme.write_text(readme.read_text() + "\n<!-- changed in v0.2.0 -->\n")
    semgrep_tpl = tpl / "template" / "{% if enable_scanners %}.semgrep.yml{% endif %}.jinja"
    _ = semgrep_tpl.write_text(semgrep_tpl.read_text() + "\n# tuned in v0.2.0\n")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.2.0 change")
    _git(tpl, "tag", "v0.2.0")

    # The real 3-way merge: update the downstream to the latest tag.
    _ = copier.run_update(
        str(dst), data=data, defaults=True, unsafe=True, overwrite=True, quiet=True
    )

    # (a) no inline conflict markers, (b) no .rej residue.
    markers = [
        p
        for p in dst.rglob("*")
        if p.is_file() and "<<<<<<< before updating" in p.read_text(errors="ignore")
    ]
    assert not markers, f"conflict markers in: {markers}"
    assert not list(dst.rglob("*.rej"))

    # (c) the always-present delta landed; the conditional one landed iff its layer is on.
    assert "<!-- changed in v0.2.0 -->" in (dst / "README.md").read_text()
    semgrep = dst / ".semgrep.yml"
    if data["enable_scanners"]:
        assert semgrep.is_file()
        assert "# tuned in v0.2.0" in semgrep.read_text()
    else:
        assert not semgrep.exists()

    # (d) the updated project is still green on its full gate.
    ci = subprocess.run(["just", "ci"], cwd=dst, capture_output=True, text=True, check=False)
    assert ci.returncode == 0, ci.stdout + ci.stderr


def test_update_overlapping_edit_surfaces_conflict_markers(
    template_root: Path, tmp_path: Path
) -> None:
    """Positive control: an overlapping edit MUST surface inline conflict markers.

    The clean-append case above proves a no-conflict update stays clean; this proves
    Copier still EMITS markers when the downstream and the template both change the
    SAME line — the actual regression net for the copier#1833 disappearing-marker
    bug class. Without it, the `no markers` assertion above could pass vacuously
    because no merge path is ever exercised.
    """
    tpl = tmp_path / "template-copy"
    _ = shutil.copytree(
        template_root,
        tpl,
        ignore=shutil.ignore_patterns(".git", ".venv", "dist", ".pytest_cache", "__pycache__"),
    )
    readme_tpl = tpl / "template" / "README.md.jinja"
    _git(tpl, "init")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.1.0")
    _git(tpl, "tag", "v0.1.0")

    dst = tmp_path / "downstream"
    _ = copier.run_copy(
        str(tpl),
        str(dst),
        data=DATA,
        defaults=True,
        unsafe=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v0.1.0",
    )
    _git(dst, "init")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "init from v0.1.0")

    # Downstream hand-edits the first README line; the template changes the SAME
    # line for v0.2.0 — a genuine 3-way conflict on `copier update`.
    dst_readme = dst / "README.md"
    dst_lines = dst_readme.read_text().splitlines()
    dst_lines[0] = "# Locally renamed title"
    _ = dst_readme.write_text("\n".join(dst_lines) + "\n")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "local edit to README title")

    tpl_lines = readme_tpl.read_text().splitlines()
    tpl_lines[0] = "# Upstream-renamed title in v0.2.0"
    _ = readme_tpl.write_text("\n".join(tpl_lines) + "\n")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.2.0 README title change")
    _git(tpl, "tag", "v0.2.0")

    _ = copier.run_update(
        str(dst), data=DATA, defaults=True, unsafe=True, overwrite=True, quiet=True
    )

    # Copier MUST surface the conflict inline — proves the marker path still works.
    assert "<<<<<<< before updating" in (dst / "README.md").read_text()
