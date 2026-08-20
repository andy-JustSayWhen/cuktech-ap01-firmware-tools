#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/ap01-check-tools
if (($# == 0)); then
    exit 0
fi
exec "$@"
