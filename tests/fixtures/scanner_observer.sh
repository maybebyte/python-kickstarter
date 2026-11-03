#!/usr/bin/env bash
# External-process observer for resource/exit tests, not the native integration.
set -eu
printf '%s\t%s\t%s\n' "${0##*/}" "$(builtin ulimit -S -s)" "$(builtin ulimit -H -s)" >> "$SCAN_EVENTS"
case "${0##*/}" in
    uvx) exit "$SCANNER_EXIT" ;;
    gitleaks) exit "$GITLEAKS_EXIT" ;;
    *) exit 99 ;;
esac
