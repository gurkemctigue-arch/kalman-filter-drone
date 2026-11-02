#!/usr/bin/env bash
# Metadata gate only; the unchanged adapter owns environment and flight lifetime.
set -euo pipefail
exec /usr/bin/python3 -I -B "$(dirname -- "$0")/formal_supplementary_preflight.py" "$@"
