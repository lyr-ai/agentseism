#!/usr/bin/env bash
# Eligibility for the coding experiment, settled before any trajectory runs and
# without invoking the model. Two conditions per instance:
#   1. the image starts and /testbed is at the base commit with a clean tree
#   2. the repository's own tests run inside the container
#
# A model is never called here, so nothing about eligibility can depend on how
# the agent behaved -- which is the point.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
OUT="${1:-/tmp/eligibility.tsv}"
printf 'instance\timage_gb\tstarts\tclean_tree\ttests_run\tverdict\n' > "$OUT"

while read -r IID; do
  [ -n "$IID" ] || continue
  IMG="docker.io/swebench/sweb.eval.x86_64.$(echo "$IID" | sed 's/__/_1776_/' | tr 'A-Z' 'a-z'):latest"
  printf '%-34s ' "$IID"
  if ! docker pull -q --platform linux/amd64 "$IMG" >/dev/null 2>&1; then
    printf 'PULL FAILED\n'; printf '%s\t-\tno\t-\t-\tINELIGIBLE\n' "$IID" >> "$OUT"; continue
  fi
  GB=$(docker image inspect "$IMG" --format '{{.Size}}' 2>/dev/null | awk '{printf "%.1f", $1/1e9}')
  R=$(docker run --rm --platform linux/amd64 "$IMG" bash -lc '
      source /opt/miniconda3/bin/activate 2>/dev/null && conda activate testbed 2>/dev/null
      cd /testbed 2>/dev/null || { echo "NOTESTBED"; exit 0; }
      DIRTY=$(git status --porcelain | wc -l | tr -d " ")
      # Grep the whole collect output for the summary line rather than guessing
      # its position. A repository can collect tens of thousands of tests and
      # still print "Interrupted: 6 errors during collection" last -- astropy
      # collects 21999 with 6 import errors from a numpy version skew, and
      # reading the last line called that a failure.
      T=$(timeout 240 python -m pytest --collect-only -q 2>&1 \
          | grep -oE "[0-9]+ tests? collected" | tail -1)
      echo "CLEAN=$DIRTY|COLLECT=${T:-none}"' 2>&1 | grep -o "CLEAN=.*" | tail -1)
  CLEAN=no; TESTS=no
  echo "$R" | grep -q 'CLEAN=0' && CLEAN=yes
  N=$(echo "$R" | grep -oE 'COLLECT=[0-9]+' | cut -d= -f2)
  [ -n "$N" ] && [ "$N" -gt 0 ] 2>/dev/null && TESTS=yes
  V=INELIGIBLE; [ "$CLEAN" = yes ] && [ "$TESTS" = yes ] && V=ELIGIBLE
  printf '%s  %sGB clean=%s tests=%s(%s)\n' "$V" "$GB" "$CLEAN" "$TESTS" "${N:-0}"
  printf '%s\t%s\tyes\t%s\t%s\t%s\n' "$IID" "$GB" "$CLEAN" "$TESTS" "$V" >> "$OUT"
done < <(cat "${INSTANCES:-/tmp/swe10.txt}"; echo)
# The process substitution appends a newline: `while read` silently drops a
# final line that has none, and the instance list written by python did. Nine
# repositories were checked instead of ten and nothing said so.

echo; echo "wrote $OUT"
awk -F'\t' 'NR>1 && $6=="ELIGIBLE"{n++} END{print n" eligible of "NR-1}' "$OUT"
