"""Native byte-precision observer/launcher for stack-boundary tests, not integration."""

import json
import os
import resource
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    if sys.argv[1] == "observe":
        limits = resource.getrlimit(resource.RLIMIT_STACK)
        _ = Path(os.environ["BYTE_EVENTS"]).write_text(json.dumps(limits))
    else:
        resource.setrlimit(
            resource.RLIMIT_STACK,
            (int(os.environ["SOFT_BYTES"]), resource.RLIM_INFINITY),
        )
        result = subprocess.run(sys.argv[1:], check=False, timeout=30)
        sys.exit(result.returncode)
