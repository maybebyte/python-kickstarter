"""REQUIRED: exercise `copier update`'s 3-way merge across a real version delta."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import copier

from tests.test_generation import MINIMAL

DATA = {**MINIMAL, "enable_precommit_install": False}


def _git(repo: Path, *args: str) -> None:
    # commit.gpgsign=false / tag.*sign=false: a global `commit.gpgsign=true` or
    # `tag.forceSignAnnotated=true` would otherwise make these commits/tags hang
    # or fail in a signing-configured environment (the maintainer's, and CI's).
    subprocess.run(  # noqa: S603, S607
        [
            "git", "-c", "user.email=t@t", "-c", "user.name=t",
            "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
            "-c", "tag.forceSignAnnotated=false", *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_update_across_versions_has_no_conflicts(template_root: Path, tmp_path: Path) -> None:
    # Work on a throwaway copy so the real template repo is never mutated.
    tpl = tmp_path / "template-copy"
    shutil.copytree(
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
    copier.run_copy(str(tpl), str(dst), data=DATA, defaults=True,
                    unsafe=True, overwrite=True, quiet=True, vcs_ref="v0.1.0")
    _git(dst, "init")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "init from v0.1.0")

    # Introduce a genuine template change and tag it v0.2.0 (the update target).
    readme = tpl / "template" / "README.md.jinja"
    readme.write_text(readme.read_text() + "\n<!-- changed in v0.2.0 -->\n")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.2.0 change")
    _git(tpl, "tag", "v0.2.0")

    # The real 3-way merge: update the downstream to the latest tag.
    copier.run_update(str(dst), data=DATA, defaults=True,
                      unsafe=True, overwrite=True, quiet=True)

    # (a) no inline conflict markers, (b) no .rej residue.
    markers = [p for p in dst.rglob("*") if p.is_file()
               and "<<<<<<< before updating" in p.read_text(errors="ignore")]
    assert not markers, f"conflict markers in: {markers}"
    assert not list(dst.rglob("*.rej"))

    # (c) the delta landed and the updated project is still green.
    assert "<!-- changed in v0.2.0 -->" in (dst / "README.md").read_text()
    ci = subprocess.run(["just", "ci"], cwd=dst, capture_output=True, text=True)  # noqa: S603, S607
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
    shutil.copytree(
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
    copier.run_copy(str(tpl), str(dst), data=DATA, defaults=True,
                    unsafe=True, overwrite=True, quiet=True, vcs_ref="v0.1.0")
    _git(dst, "init")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "init from v0.1.0")

    # Downstream hand-edits the first README line; the template changes the SAME
    # line for v0.2.0 — a genuine 3-way conflict on `copier update`.
    dst_readme = dst / "README.md"
    dst_lines = dst_readme.read_text().splitlines()
    dst_lines[0] = "# Locally renamed title"
    dst_readme.write_text("\n".join(dst_lines) + "\n")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-m", "local edit to README title")

    tpl_lines = readme_tpl.read_text().splitlines()
    tpl_lines[0] = "# Upstream-renamed title in v0.2.0"
    readme_tpl.write_text("\n".join(tpl_lines) + "\n")
    _git(tpl, "add", "-A")
    _git(tpl, "commit", "-m", "v0.2.0 README title change")
    _git(tpl, "tag", "v0.2.0")

    copier.run_update(str(dst), data=DATA, defaults=True,
                      unsafe=True, overwrite=True, quiet=True)

    # Copier MUST surface the conflict inline — proves the marker path still works.
    assert "<<<<<<< before updating" in (dst / "README.md").read_text()
