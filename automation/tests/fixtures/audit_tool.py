"""Real locked export, controlled audit-service failure, inert unrelated CI tools."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast


def main() -> int:
    """Observe the complete gate at the uv process boundary."""
    args = sys.argv[1:]
    if args and args[0] == "export":
        failure = int(os.environ["EXPORT_EXIT"])
        if failure:
            return failure
        executable = os.environ["REAL_UV"]
        pid = os.posix_spawn(executable, [executable, *args], dict(os.environ))
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status)
    if args[:2] == ["run", "pip-audit"]:
        parser = argparse.ArgumentParser()
        _ = parser.add_argument("-r", "--requirement", required=True)
        _ = parser.add_argument("--no-deps", action="store_true")
        _ = parser.add_argument("--disable-pip", action="store_true")
        options = cast("dict[str, object]", vars(parser.parse_args(args[2:])))
        requirement = options["requirement"]
        assert isinstance(requirement, str)
        content = Path(requirement).read_text()
        packages = [
            line.split("==")[0]
            for line in content.splitlines()
            if "==" in line and not line.startswith("#")
        ]
        with Path(os.environ["AUDIT_OBSERVATIONS"]).open("a") as stream:
            _ = stream.write(json.dumps(packages) + "\n")
        return int(os.environ["AUDIT_EXIT"]) if packages else 0
    if args[:1] == ["run"] and len(args) > 1 and args[1] in {"ruff", "basedpyright", "pytest"}:
        return 0
    return 29


if __name__ == "__main__":
    sys.exit(main())
