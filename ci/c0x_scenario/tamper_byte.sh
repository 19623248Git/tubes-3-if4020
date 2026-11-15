#!/bin/sh
set -eu

file="${1:?usage: tamper_byte.sh <file> [offset]}"
size="$(wc -c < "$file")"
offset="${2:-$((size / 2))}"

if [ "$offset" -ge "$size" ]; then
  echo "offset $offset is past the end of $file ($size bytes)" >&2
  exit 2
fi

sha256sum "$file"
old="$(od -An -tu1 -j "$offset" -N 1 "$file" | tr -d ' ')"
new=$(((old + 1) % 256))
printf "\\$(printf '%03o' "$new")" | dd of="$file" bs=1 seek="$offset" count=1 conv=notrunc 2>/dev/null

echo "byte $offset changed from $old to $new, size $size -> $(wc -c < "$file")"
sha256sum "$file"