#!/usr/bin/env bash
# Configure only a disposable caller, then prove the real entrypoint leaves it alone.
set -eu
builtin ulimit -S -s "$INITIAL_SOFT"
builtin ulimit -H -s "$INITIAL_HARD"
printf 'before\t%s\t%s\n' "$(builtin ulimit -S -s)" "$(builtin ulimit -H -s)" >> "$SCAN_EVENTS"
status=0
"$@" || status=$?
printf 'after\t%s\t%s\n' "$(builtin ulimit -S -s)" "$(builtin ulimit -H -s)" >> "$SCAN_EVENTS"
exit "$status"
