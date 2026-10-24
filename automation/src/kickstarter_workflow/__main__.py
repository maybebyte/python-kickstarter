"""JSON command-line interface for the public workflow."""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from kickstarter_workflow.records import Record, WorkflowError, load
from kickstarter_workflow.workflow import Workflow


@dataclass
class _Arguments(argparse.Namespace):
    state: str = ""
    operation: str = ""
    request: str = ""


def main(argv: list[str] | None = None) -> int:
    """Execute a request file and emit one JSON outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--state", required=True)
    _ = parser.add_argument(
        "operation", choices=("prepare", "resume", "status", "verify", "return", "cleanup")
    )
    _ = parser.add_argument("request")
    arguments = parser.parse_args(argv, namespace=_Arguments())
    try:
        request = load(Path(arguments.request).absolute())
        result = Workflow(Path(arguments.state).absolute()).dispatch(arguments.operation, request)
    except (WorkflowError, OSError, ValueError) as error:
        result: Record = {"status": "blocked", "reason": str(error)}
    _ = sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0 if result["status"] in {"prepared", "exempt", "verified", "returned", "cleaned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
