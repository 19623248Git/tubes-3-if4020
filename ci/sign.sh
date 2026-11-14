#!/bin/sh
set -eu

: "${IMAGE:?set IMAGE}"
: "${PACKAGE:?set PACKAGE}"
: "${VERSION:?set VERSION}"
ARTIFACT="${ARTIFACT:-dist/app.zip}"
OUT_DIR="${OUT_DIR:-out}"
BUNDLE_NAME="${BUNDLE_NAME:-rilis.json}"

if [ -n "${SIGNING_KEY_PEM:-}" ]; then
  SIGNING_KEY_FILE="$(umask 077 && mktemp)"
  trap 'rm -f "$SIGNING_KEY_FILE"' 0
  trap 'exit 1' HUP INT TERM
  printf '%s\n' "$SIGNING_KEY_PEM" > "$SIGNING_KEY_FILE"
fi
: "${SIGNING_KEY_FILE:?set SIGNING_KEY_PEM or SIGNING_KEY_FILE}"

if [ ! -f "$SIGNING_KEY_FILE" ]; then
  echo "signing key file not found" >&2
  exit 2
fi
KEY_ABS="$(cd "$(dirname "$SIGNING_KEY_FILE")" && pwd)/$(basename "$SIGNING_KEY_FILE")"
ART_DIR="$(cd "$(dirname "$ARTIFACT")" && pwd)"
mkdir -p "$OUT_DIR"
OUT_ABS="$(cd "$OUT_DIR" && pwd)"

docker pull "$IMAGE"

docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -v "$ART_DIR:/input:ro" \
  -v "$OUT_ABS:/output" \
  -v "$KEY_ABS:/run/signing.key.pem:ro" \
  "$IMAGE" sign --file "/input/$(basename "$ARTIFACT")" \
  --package "$PACKAGE" --version "$VERSION" \
  --key /run/signing.key.pem --out "/output/$BUNDLE_NAME"

echo "signed $ARTIFACT -> $OUT_DIR/$BUNDLE_NAME"