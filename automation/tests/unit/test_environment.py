"""Declared product dependencies and package data survive workbench preparation."""

from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, text
from kickstarter_workflow.workflow import Workflow
from tests.unit.test_transfer import review


def test_declared_product_dependency_is_available_before_policy_freeze(
    tmp_path: Path, plan: Record
) -> None:
    source = Path(text(plan, "source"))
    metadata = (
        '[project]\nname = "original-product"\nversion = "1.0.0"\n'
        'requires-python = ">=3.11"\ndependencies = ["humanize==4.13.0"]\n'
    )
    _ = (source / "pyproject.toml").write_text(metadata)
    _ = (source / "app.py").write_text(
        '"""Product dependency fixture."""\n\nimport humanize\n\n\ndef twice(value: int) -> str:\n    """Format a doubled value."""\n    return humanize.intcomma(value * 2)\n'
    )
    test = source / "test_app.py"
    _ = test.write_text(test.read_text().replace("== 6", '== "6"'))
    mapping = plan["mapping"]
    assert isinstance(mapping, list)
    mapping.append(
        {"source": "pyproject.toml", "target": "product/pyproject.toml", "role": "context"}
    )
    plan["environment"] = {"project": "pyproject.toml", "groups": [], "extras": []}
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    frozen = (workspace / "pyproject.toml").read_bytes()
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    assert verified["product_coverage"] == 100
    assert (workspace / "pyproject.toml").read_bytes() == frozen
    assert (source / "pyproject.toml").read_text() == metadata
    assert 'name = "humanize"' in (workspace / "uv.lock").read_text()


def test_local_package_metadata_assets_and_destination_imports_are_preserved(
    tmp_path: Path, plan: Record
) -> None:
    source = Path(text(plan, "source"))
    (source / "app.py").unlink()
    package = source / "src/original_product"
    package.mkdir(parents=True)
    _ = (package / "label.txt").write_text("Double")
    _ = (package / "__init__.py").write_text(
        '"""Installed product."""\n\nfrom importlib.resources import files\n\nimport humanize\n\n\ndef twice(value: int) -> str:\n    """Use packaged data and a declared dependency."""\n    label = files("original_product").joinpath("label.txt").read_text()\n    return label + " " + humanize.intcomma(value * 2)\n'
    )
    metadata = '[project]\nname = "original-product"\nversion = "1.0.0"\nrequires-python = ">=3.11"\ndependencies = ["humanize==4.13.0"]\nreadme = "README.md"\n[build-system]\nrequires = ["uv_build==0.11.23"]\nbuild-backend = "uv_build"\n'
    _ = (source / "pyproject.toml").write_text(metadata)
    _ = (source / "test_app.py").write_text(
        '"""Real distribution and execution layout."""\n\nfrom importlib.metadata import version\nfrom pathlib import Path\n\nimport original_product\n\n\ndef test_package() -> None:\n    assert original_product.twice(3) == "Double 6"\n    assert version("original-product") == "1.0.0"\n    assert original_product.__file__ is not None\n    assert Path(original_product.__file__).is_relative_to(Path(__file__).parent / "src")\n'
    )
    plan["mapping"] = [
        {"source": name, "target": "product/" + name, "role": role}
        for name, role in [
            ("src/original_product/__init__.py", "source"),
            ("src/original_product/label.txt", "context"),
            ("test_app.py", "test"),
            ("pyproject.toml", "context"),
            ("README.md", "context"),
        ]
    ]
    plan["environment"] = {"project": "pyproject.toml", "groups": [], "extras": []}
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    module = workspace / "product/src/original_product/__init__.py"
    _ = module.write_text(module.read_text().replace("value * 2", "value + value"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    result = workflow.dispatch(
        "return", review(text(verified, "receipt"), "src/original_product/__init__.py")
    )
    assert result["status"] == "returned", result
    assert result["destination_validated"] is True
    assert (source / "pyproject.toml").read_text() == metadata


@pytest.mark.parametrize(
    "damage",
    [
        "mapping",
        "missing-selection",
        "dynamic",
        "uv-sources",
        "backend",
        "groups",
        "extras",
        "compatibility",
    ],
)
def test_unsupported_product_environments_block_before_readiness(
    tmp_path: Path, plan: Record, damage: str
) -> None:
    source = Path(text(plan, "source"))
    metadata = '[project]\nname = "original-product"\nversion = "1.0.0"\nrequires-python = ">=3.11"\ndependencies = []\n'
    if damage == "dynamic":
        metadata += 'dynamic = ["version"]\n'
    elif damage == "uv-sources":
        metadata += '[tool.uv.sources]\nexternal = { path = "../other" }\n'
    elif damage == "backend":
        metadata += (
            '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n'
        )
    elif damage == "compatibility":
        metadata = metadata.replace(">=3.11", "<3.10")
    _ = (source / "pyproject.toml").write_text(metadata)
    mapping = plan["mapping"]
    assert isinstance(mapping, list)
    if damage != "mapping":
        mapping.append(
            {"source": "pyproject.toml", "target": "product/pyproject.toml", "role": "context"}
        )
    if damage != "missing-selection":
        plan["environment"] = {
            "project": "pyproject.toml",
            "groups": ["undeclared"] if damage == "groups" else [],
            "extras": ["undeclared"] if damage == "extras" else [],
        }
    result = Workflow(tmp_path / "state").dispatch("prepare", plan)
    assert result["status"] == "blocked", result
    assert (source / "pyproject.toml").read_text() == metadata
