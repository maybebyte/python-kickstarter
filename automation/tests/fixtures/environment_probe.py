"""Report only the environment keys explicitly requested by a fixture test."""

import json
import os
import sys

if __name__ == "__main__":
    _ = sys.stdout.write(json.dumps({key: os.environ.get(key) for key in sys.argv[1:]}) + "\n")
