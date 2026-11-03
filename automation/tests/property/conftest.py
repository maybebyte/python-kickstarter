"""Hypothesis profiles and property-marker enforcement for the property suite."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

settings.register_profile("dev", max_examples=25, deadline=None)
settings.register_profile(
    "ci",
    max_examples=300,
    deadline=None,
    derandomize=True,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

_HERE = Path(__file__).parent


def _require_property_marker(items: list[pytest.Item]) -> None:
    # Test the real marker, not `item.keywords` — the parent dir is named
    # "property", so "property" is a node keyword on every item here regardless.
    unmarked = [
        item.nodeid
        for item in items
        if item.path.is_relative_to(_HERE) and item.get_closest_marker("property") is None
    ]
    if unmarked:
        listed = ", ".join(unmarked)
        msg = f"tests/property/ files must set the property marker (missing: {listed})"
        raise pytest.UsageError(msg)


@pytest.hookimpl(hookwrapper=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> Generator[None, object]:
    """Enforce the property marker before `-m property` deselects (and hides) violators.

    `just fuzz` runs `-m property`; an unmarked file here would otherwise be
    silently deselected and run in no gate. Snapshot the fully-collected items
    before the marker expression runs, then check after.
    """
    snapshot = list(items)
    yield
    _require_property_marker(snapshot)
