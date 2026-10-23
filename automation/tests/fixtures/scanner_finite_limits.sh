#!/usr/bin/env bash
# Finite-limit property driver; only the disposable child changes resource limits.
set -eu
ulimit -S -s "$SOFT"
ulimit -H -s "$HARD"
uvx() {
    printf 'scanner\t%s\t%s\n' "$(ulimit -S -s)" "$(ulimit -H -s)" >> "$EVENTS"
}
gitleaks() {
    printf 'later\t%s\t%s\n' "$(ulimit -S -s)" "$(ulimit -H -s)" >> "$EVENTS"
}
export -f uvx gitleaks
just --quiet --justfile "$1" scan
printf 'caller\t%s\t%s\n' "$(ulimit -S -s)" "$(ulimit -H -s)" >> "$EVENTS"
