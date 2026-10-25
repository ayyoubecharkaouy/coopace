#!/bin/sh
# Use the local SDK when available, otherwise the Go installation on PATH.
set -eu

coopace_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
coopace_version=$(cat "$coopace_root/.go-version")
coopace_go="$coopace_root/.local/toolchains/go$coopace_version/bin/go"

if [ ! -x "$coopace_go" ]; then
    if command -v go >/dev/null 2>&1; then
        coopace_go=$(command -v go)
    else
        printf '%s\n' 'Go is unavailable. Run: sh scripts/setup-go.sh (see docs/DEVELOPMENT.md).' >&2
        exit 1
    fi
fi

mkdir -p "$coopace_root/.cache/go-build" "$coopace_root/.local/go"
export GOCACHE="$coopace_root/.cache/go-build"
export GOPATH="$coopace_root/.local/go"
export GOTOOLCHAIN=local
cd "$coopace_root"
exec "$coopace_go" "$@"
