#!/bin/sh
set -eu

: "${GITHUB_REPOSITORY:?run inside GitHub Actions or set GITHUB_REPOSITORY}"
: "${GITHUB_REF_TYPE:?set GITHUB_REF_TYPE to branch or tag}"
: "${GITHUB_REF_NAME:?set GITHUB_REF_NAME}"
: "${GITHUB_SHA:?set GITHUB_SHA}"
GITHUB_SERVER_URL="${GITHUB_SERVER_URL:-https://github.com}"

image="ghcr.io/$(echo "$GITHUB_REPOSITORY" | tr '[:upper:]' '[:lower:]')"

if [ "$GITHUB_REF_TYPE" = "tag" ]; then
  signer_ver="$(sed -n 's/^version *= *"\(.*\)"/\1/p' signer/pyproject.toml | head -n 1)"
  if [ "v$signer_ver" != "$GITHUB_REF_NAME" ]; then
    echo "tag $GITHUB_REF_NAME does not match signer/pyproject.toml version $signer_ver" >&2
    exit 1
  fi
  tag="$GITHUB_REF_NAME"
  kind="release"
else
  tag="sha-$(echo "$GITHUB_SHA" | cut -c 1-7)"
  kind="development"
fi

if [ -n "${GHCR_TOKEN:-}" ]; then
  : "${GITHUB_ACTOR:?set GITHUB_ACTOR}"
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
fi

# shellcheck disable=SC2086
docker build --platform linux/amd64 -f signer/Dockerfile -t "$image:$tag" \
  --label "org.opencontainers.image.source=$GITHUB_SERVER_URL/$GITHUB_REPOSITORY" \
  --label "org.opencontainers.image.revision=$GITHUB_SHA" \
  --label "org.opencontainers.image.version=$tag" \
  signer

docker push "$image:$tag"

pinned="$(docker image inspect --format '{{index .RepoDigests 0}}' "$image:$tag")"
echo "Pinned reference ($kind): $pinned"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Image published ($kind build)"
    echo ""
    echo "| Git ref | Image tags | Pinned reference |"
    echo "|---|---|---|"
    echo "| \`$GITHUB_REF_NAME\` | \`$tag\` | \`$pinned\` |"
  } >> "$GITHUB_STEP_SUMMARY"
fi