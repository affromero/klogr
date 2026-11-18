#!/usr/bin/env bash
# Pre-commit hook: keep dynamic loader configuration out of runtime code.
# Configure loader paths in shell startup or machine bootstrap.

set -euo pipefail

has_violation=0

for file in "$@"; do
    [[ -f "$file" ]] || continue

    case "$file" in
        *.md | \
        *.rst | \
        *.txt)
            continue
            ;;
    esac

    if ! grep -Iq . "$file"; then
        continue
    fi

    hits=$(
        grep -nHE 'LD_LIBRARY_PATH|LD_PRELOAD' "$file" \
            | grep -Ev 'env\.pop\("LD_PRELOAD", None\)|env -u LD_PRELOAD|unset LD_PRELOAD|setenv\("LD_PRELOAD"|"LD_PRELOAD":|LD_PRELOAD:-|not in (env|captured_env)|PRELOAD_PATH|preload_path|preload_so_path' \
            || true
    )
    if [[ -n "$hits" ]]; then
        printf '%s\n' "$hits"
        has_violation=1
    fi
done

if [[ "$has_violation" -ne 0 ]]; then
    cat >&2 <<'EOF'
ERROR: LD_LIBRARY_PATH/LD_PRELOAD must not be set in runtime code.

Put dynamic loader configuration in shell startup or machine bootstrap
setup instead, e.g. ~/.bashrc.
EOF
    exit 1
fi
