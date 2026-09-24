#!/bin/bash
# Finder opens .command files in Terminal; keep the result visible there.
KICHO_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
/bin/bash "$KICHO_ROOT/scripts/setup-macos.sh" "$@"
KICHO_EXIT=$?
if [ -t 0 ]; then
    printf '\nEnterキーで閉じます。'
    read -r _
fi
exit "$KICHO_EXIT"
