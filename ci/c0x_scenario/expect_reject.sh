#!/bin/sh
set -eu

: "${EXPECTED_EXIT:?set EXPECTED_EXIT}"
: "${EXPECTED_STATUS:?set EXPECTED_STATUS}"
RESULT="${RESULT:-out/verification.json}"
export RESULT

code=0
sh "$(dirname "$0")/verify.sh" || code=$?

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "verify_exit=$code" >> "$GITHUB_OUTPUT"
fi

if [ "$code" -ne "$EXPECTED_EXIT" ]; then
  echo "FAIL: expected exit $EXPECTED_EXIT, got $code" >&2
  exit 1
fi
if ! grep -Eq "\"status\"[[:space:]]*:[[:space:]]*\"$EXPECTED_STATUS\"" "$RESULT"; then
  echo "FAIL: expected status $EXPECTED_STATUS in $RESULT" >&2
  exit 1
fi

echo "PASS: rejected with exit $code and status $EXPECTED_STATUS"