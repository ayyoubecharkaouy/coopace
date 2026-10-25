#!/bin/sh
# Install the pinned official SDK locally, without changing the system or PATH.
set -eu

coopace_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
coopace_version=$(cat "$coopace_root/.go-version")
coopace_destination="$coopace_root/.local/toolchains/go$coopace_version"

if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    printf '%s\n' 'This installer supports Linux x86_64. See docs/DEVELOPMENT.md for other systems.' >&2
    exit 1
fi

case "$coopace_version" in
    1.27.3) coopace_sha256=65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 ;;
    *) printf 'No verified archive configured for Go %s.\n' "$coopace_version" >&2; exit 1 ;;
esac

if [ -d "$coopace_destination" ]; then
    if [ -x "$coopace_destination/bin/go" ]; then
        "$coopace_destination/bin/go" version
        exit 0
    fi
    printf 'Incomplete installation at %s; inspect it before retrying.\n' "$coopace_destination" >&2
    exit 1
fi

for coopace_command in curl sha256sum tar mktemp; do
    if ! command -v "$coopace_command" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$coopace_command" >&2
        exit 1
    fi
done

coopace_archive="go$coopace_version.linux-amd64.tar.gz"
coopace_cached_archive="$coopace_root/.cache/downloads/$coopace_archive"
mkdir -p "$coopace_root/.local/toolchains" "$coopace_root/.cache/downloads"

coopace_verify_archive() {
    [ -f "$coopace_cached_archive" ] &&
        printf '%s  %s\n' "$coopace_sha256" "$coopace_cached_archive" | sha256sum --check --status
}

if ! coopace_verify_archive; then
    printf 'Downloading or resuming official Go %s archive...\n' "$coopace_version"
    if curl --fail --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 30 --speed-limit 1 --speed-time 120 \
        --continue-at - --output "$coopace_cached_archive" \
        "https://go.dev/dl/$coopace_archive"; then
        :
    else
        coopace_status=$?
        printf '\nDownload interrupted. Partial archive kept at:\n%s\nRun this script again to resume.\n' \
            "$coopace_cached_archive" >&2
        exit "$coopace_status"
    fi
fi

if ! coopace_verify_archive; then
    printf 'Archive checksum mismatch. Installation stopped.\nRemove this cached file before retrying:\n%s\n' \
        "$coopace_cached_archive" >&2
    exit 1
fi

coopace_temporary=$(mktemp -d "$coopace_root/.local/toolchains/.extract.XXXXXX")
trap 'rm -rf -- "$coopace_temporary"' EXIT
trap 'exit 1' HUP INT TERM

tar -xzf "$coopace_cached_archive" -C "$coopace_temporary"
mv -- "$coopace_temporary/go" "$coopace_destination"
"$coopace_destination/bin/go" version
printf '%s\n' 'Ready. Run: sh scripts/go.sh test ./...'
