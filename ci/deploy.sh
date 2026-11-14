#!/bin/sh
set -eu

ARTIFACT="${ARTIFACT:-dist/app.zip}"
OUT_DIR="${OUT_DIR:-out}"
MARKER="$OUT_DIR/deployed.marker"

if [ ! -f "$ARTIFACT" ]; then
  echo "artifact not found: $ARTIFACT" >&2
  exit 1
fi
sha="$(sha256sum "$ARTIFACT" | cut -d ' ' -f 1)"
mkdir -p "$OUT_DIR"

{
  echo "artifact=$(basename "$ARTIFACT")"
  echo "sha256=$sha"
  echo "commit=${GITHUB_SHA:-local}"
  echo "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$MARKER"

cat "$MARKER"