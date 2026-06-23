#!/usr/bin/env bash
# Build the noegress LD_PRELOAD egress blocker.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gcc -shared -fPIC -o "$here/noegress.so" "$here/noegress.c" -ldl
echo "built $here/noegress.so"
