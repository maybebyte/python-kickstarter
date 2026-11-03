"""Run only the finite-limit property after lowering this child's inherited ceiling."""

import os
import resource
import sys
from pathlib import Path

import pytest


class Reports:
    def __init__(self, output: Path) -> None:
        self.output: Path = output

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" or report.skipped:
            with self.output.open("a") as stream:
                _ = stream.write(f"{report.when}\t{report.nodeid}\t{report.outcome}\n")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    output = Path(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_STACK, (4194304, 4194304))
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    _ = output.write_text(f"host\t{soft}\t{hard}\n")
    os.chdir(root)
    return pytest.main(
        [
            "tests/property/test_scanner_limits.py::test_finite_limits_are_preserved",
            "--no-cov",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(output.parent / "child-tmp"),
        ],
        plugins=[Reports(output)],
    )


if __name__ == "__main__":
    raise SystemExit(main())
