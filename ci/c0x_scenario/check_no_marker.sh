#!/bin/sh
set -eu

OUT_DIR="${OUT_DIR:-out}"
MARKER="$OUT_DIR/deployed.marker"

ls -la "$OUT_DIR"
if [ -e "$MARKER" ]; then
  echo "$MARKER exists: deploy ran" >&2
  exit 1
fi
echo "no $MARKER: deploy did not run"