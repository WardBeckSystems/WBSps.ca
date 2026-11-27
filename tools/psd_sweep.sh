#!/bin/bash
# psd_sweep.sh CLONE...: the PSDs a repo already holds become JPEGs (tools/psd_to_jpg.py), committed and pushed.
cd "$(dirname "$0")/.."
for c in "$@"; do
  [ -n "$(find "$c" -path "$c/.git" -prune -o -type f -iname '*.psd' -print -quit)" ] || continue
  python3 tools/psd_to_jpg.py "$c" --git || { echo "FAIL convert $c"; continue; }
  if [ -f "$c/.gitattributes" ] && grep -qi 'psd' "$c/.gitattributes"; then
    grep -vi '\.psd[[:space:]]' "$c/.gitattributes" > "$c/.gitattributes.new"; mv "$c/.gitattributes.new" "$c/.gitattributes"
    git -C "$c" add .gitattributes
  fi
  git -C "$c" add -A -- . ':!*.psd'
  git -C "$c" commit -q -m "PSDs are JPEGs now (flattened, quality 92)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && git -C "$c" push -q origin HEAD && echo "swept $c: $(git -C "$c" log --oneline -1)"
done
