# BASH_ENV fault injection: fail one limit operation, keep all others real.
ulimit() {
    if [[ "$*" == "$LIMIT_FAULT" ]]; then
        return 73
    fi
    builtin ulimit "$@"
}
