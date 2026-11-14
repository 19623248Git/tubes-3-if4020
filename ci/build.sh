#!/bin/sh
set -eu

mkdir -p dist
rm -f dist/app.zip
(cd app && zip -q -r -X ../dist/app.zip .)

echo "built dist/app.zip ($(wc -c < dist/app.zip) bytes)"
sha256sum dist/app.zip