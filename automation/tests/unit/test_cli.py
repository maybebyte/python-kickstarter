"""The installed entrypoint uses the same durable workflow as Python callers."""

import json
from pathlib import Path

import pytest

from kickstarter_workflow.__main__ import main


def test_cli_emits_structured_exemption_and_rejects_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    _ = request.write_text(
        json.dumps(
            {"project": "demo", "task": "one", "mode": "disposable", "reason": "one-off probe"}
        )
    )
    args = ["--state", str(tmp_path / "state"), "prepare", str(request)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "exempt"
    _ = request.write_text("not json")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
