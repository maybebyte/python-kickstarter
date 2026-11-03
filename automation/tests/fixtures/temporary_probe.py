"""Observe the runner's temporary environment in a real child process."""

import json
import os
import sys
import tempfile
from pathlib import Path

if __name__ == "__main__":
    result = {"TMPDIR": os.environ["TMPDIR"]}
    if sys.argv[1:] == ["create"]:
        with tempfile.NamedTemporaryFile(dir=os.environ["TMPDIR"]) as stream:
            result["parent"] = str(Path(stream.name).parent)
    _ = sys.stdout.write(json.dumps(result) + "\n")
