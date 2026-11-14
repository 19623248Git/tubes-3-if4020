#!/bin/sh
set -eu

: "${IMAGE:?set IMAGE}"
: "${PACKAGE:?set PACKAGE}"
: "${VERSION:?set VERSION}"
ARTIFACT="${ARTIFACT:-dist/app.zip}"
BUNDLE="${BUNDLE:-out/rilis.json}"
TRUST_STORE="${TRUST_STORE:-ci/trust.json}"
RESULT="${RESULT:-out/verification.json}"

abs_dir() { (cd "$(dirname "$1")" && pwd); }
ART_DIR="$(abs_dir "$ARTIFACT")"
BUNDLE_DIR="$(abs_dir "$BUNDLE")"
TRUST_DIR="$(abs_dir "$TRUST_STORE")"
mkdir -p "$(dirname "$RESULT")"

docker pull "$IMAGE"

status=0
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -v "$ART_DIR:/input:ro" \
  -v "$BUNDLE_DIR:/bundle:ro" \
  -v "$TRUST_DIR:/trust:ro" \
  "$IMAGE" verify --file "/input/$(basename "$ARTIFACT")" \
  --bundle "/bundle/$(basename "$BUNDLE")" \
  --trust-store "/trust/$(basename "$TRUST_STORE")" \
  --package "$PACKAGE" --version "$VERSION" --json \
  > "$RESULT" || status=$?

cat "$RESULT"
echo "verify exit code: $status"
exit "$status"