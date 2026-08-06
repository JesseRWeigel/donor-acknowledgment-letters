#!/usr/bin/env bash
# The whole claim, checked. Exit code is the only thing that counts as a result.
#
# Each layer prints ok or bad. Nothing here reports success for a step it did not run, and
# anything that cannot run is a failure rather than a skip, because a skipped check and a passing
# check look identical in a log a week later.
set -uo pipefail
cd "$(dirname "$0")/.."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  BAD  %s\n' "$1"; FAILED=1; }

echo "== 1. the package imports and the sources parse"
if python3 -m compileall -q donorack scripts tests >"$TMP/compile.log" 2>&1; then
  ok "every source file compiles"
else bad "a source file does not compile"; cat "$TMP/compile.log"; fi
if python3 -c "import donorack.audit, donorack.cli, donorack.csvin, donorack.letter, \
donorack.pdfwrite, donorack.rules" 2>"$TMP/import.log"; then
  ok "the package imports with nothing installed beyond the standard library"
else bad "the package does not import"; cat "$TMP/import.log"; fi

echo "== 2. the unit suite"
if python3 -m unittest discover -s tests -t . >"$TMP/unit.log" 2>&1; then
  ok "$(grep -oE 'Ran [0-9]+ tests' "$TMP/unit.log" | tail -1) passed"
else bad "the unit suite failed"; tail -30 "$TMP/unit.log"; fi

echo "== 3. the clean corpus generates letters and exits zero"
if python3 -m donorack.cli letters --csv corpus/donations.csv --charity corpus/charity.json \
     --out "$TMP/out" >"$TMP/letters.log" 2>&1; then
  n_txt=$(find "$TMP/out" -name '*.txt' | wc -l)
  n_pdf=$(find "$TMP/out" -name '*.pdf' | wc -l)
  n_row=$(($(wc -l < corpus/donations.csv) - 1))
  if [ "$n_txt" -eq "$n_row" ] && [ "$n_pdf" -eq "$n_row" ]; then
    ok "$n_txt letters and $n_pdf PDFs from $n_row donations"
  else bad "$n_row donations produced $n_txt letters and $n_pdf PDFs"; fi
else bad "generation over the clean corpus exited non-zero"; cat "$TMP/letters.log"; fi

echo "== 4. a corpus with bad rows exits non-zero and names every line"
python3 -m donorack.cli letters --csv corpus/problem-rows.csv --charity corpus/charity.json \
  --out "$TMP/bad" >"$TMP/bad.log" 2>&1
if [ $? -eq 0 ]; then bad "a file with six unusable rows was reported as a success"
else
  missing=""
  for line in 2 3 4 5 6 7; do
    grep -q "row $line:" "$TMP/bad.log" || missing="$missing $line"
  done
  if [ -z "$missing" ]; then ok "all six bad rows reported with their line numbers"
  else bad "no report for line(s):$missing"; fi
fi

echo "== 5. every generated PDF still audits clean after extraction"
# The end to end claim. The auditor reads text pulled back out of the finished PDF, so this is
# the document a donor would actually receive rather than the string that went into it.
if python3 -m donorack.cli audit "$TMP"/out/*.pdf --csv corpus/donations.csv \
     --charity corpus/charity.json >"$TMP/audit.log" 2>&1; then
  ok "$(grep -oE '[0-9]+ letters checked, [0-9]+ with defects' "$TMP/audit.log")"
else bad "a generated PDF failed its own audit"; tail -20 "$TMP/audit.log"; fi

echo "== 6. and a defect introduced into one PDF is caught"
# Layer 5 alone would pass if the auditor were reading nothing at all.
python3 - "$TMP" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "out" / "2026-05-09-sam-ito.txt"
marker = "No goods or services were provided to you in exchange for this contribution."
text = p.read_text(encoding="utf-8")
assert marker in text, "the mutation target is gone, so layer 6 proves nothing"
(p.parent / "tampered.txt").write_text(text.replace(marker, ""), encoding="utf-8")
PY
python3 -m donorack.cli audit "$TMP/out/tampered.txt" --csv corpus/donations.csv \
  --charity corpus/charity.json >"$TMP/tamper.log" 2>&1
if [ $? -ne 0 ] && grep -q "no goods or services statement" "$TMP/tamper.log"; then
  ok "the missing sentence was found and the command exited non-zero"
else bad "a letter missing the required negative statement passed"; cat "$TMP/tamper.log"; fi
rm -f "$TMP/out/tampered.txt"

echo "== 7. the independent checker agrees, and imports nothing from the package"
# Proved by walking the import graph rather than grepping for the word, because a grep is
# satisfied by a comment and misses `importlib.import_module`.
if python3 scripts/check_imports.py scripts/check_independent.py donorack >"$TMP/graph.log" 2>&1
then ok "$(tail -1 "$TMP/graph.log")"
else bad "the independent checker is not independent"; cat "$TMP/graph.log"; fi
if python3 scripts/check_independent.py "$TMP/out" corpus/donations.csv >"$TMP/ind.log" 2>&1; then
  ok "$(grep -oE '[0-9]+ independent checks, [0-9]+ failed' "$TMP/ind.log")"
else bad "the independent checker disagrees"; grep -E 'FAIL' "$TMP/ind.log" | head -20; fi

echo "== 8. year-end summaries"
if python3 -m donorack.cli summaries --csv corpus/donations.csv --charity corpus/charity.json \
     --out "$TMP/sum" --year 2026 >"$TMP/sum.log" 2>&1; then
  dana="$TMP/sum/2026-summary-dana-okonkwo.txt"
  if grep -q '\$400\.00' "$dana" && grep -q 'does not replace those letters' "$dana"; then
    ok "four gifts of \$100 total \$400 and the summary says it is not an acknowledgment"
  else bad "the summary is wrong or omits the disclaimer"; fi
else bad "summary generation failed"; cat "$TMP/sum.log"; fi

echo "== 9. sabotage, under the three-gate rule"
if python3 scripts/sabotage.py --all >"$TMP/sab.log" 2>&1; then
  ok "$(grep -oE '[0-9]+/[0-9]+ sabotages proven' "$TMP/sab.log")"
  grep -E 'null control' "$TMP/sab.log" | sed 's/^ */       /'
else bad "a sabotage was a no-op or went unnoticed"; grep -vE 'CAUGHT' "$TMP/sab.log" | head -20
fi

echo "== 10. nothing private is in any tracked file"
# The patterns are ASSEMBLED rather than written out, because a scanner whose own pattern list is
# a tracked file matches itself. Excluding this file would be the easy fix and would also stop it
# finding a real leak here.
TILDE="~"; H="ho""me"; SK="s""k-"; GH="gh""p_"; AK="AK""IA"
PATTERNS=("/$H/[a-z]" "$TILDE/Projects" "$AK[0-9A-Z]" "$SK[A-Za-z0-9]\{20\}" \
          "$GH[A-Za-z0-9]" "BEGIN [A-Z ]*PRIVATE KEY")

scan() {  # scan <extra-file-or-empty>; prints the tracked files matching any pattern
  { git ls-files; [ -n "${1:-}" ] && echo "$1"; } | sort -u | while read -r f; do
    [ -f "$f" ] || continue
    for pat in "${PATTERNS[@]}"; do
      grep -lI "$pat" "$f" 2>/dev/null
    done
  done | sort -u
}

TRACKED=$(git ls-files | wc -l)
if [ "$TRACKED" -lt 10 ]; then
  # Before the first commit `git ls-files` is empty and this layer passes without reading
  # anything. A check that cannot fail is worse than no check, so an empty file set is a failure.
  bad "only $TRACKED tracked files, so the privacy scan had almost nothing to read"
else
  # Positive control first. If the scanner cannot find a leak that is definitely there, its
  # silence on the real files means nothing.
  printf 'token %s%s\n' "$GH" "AAAAAAAAAAAAAAAAAAAA" > "$TMP/_planted_leak.txt"
  if [ -n "$(scan "$TMP/_planted_leak.txt")" ]; then
    ok "the scanner finds a planted credential, so its silence below is informative"
  else bad "the scanner missed a planted credential, so this layer proves nothing"; fi
  rm -f "$TMP/_planted_leak.txt"

  HITS=$(scan)
  if [ -z "$HITS" ]; then
    ok "no home paths, no keys, no private repository names in $TRACKED tracked files"
  else bad "private content in a tracked file"; echo "$HITS" | sed 's/^/         /'; fi
fi
if grep -q '00-1234567' corpus/charity.json; then
  ok "the demo EIN uses prefix 00, which the IRS never issues, so it cannot be a real charity"
else bad "the demo charity's EIN is not the unissuable placeholder"; fi

echo "== 11. the published page is the current output, not a stale copy"
# docs/index.html is generated from the corpus. Rebuilding it and comparing against what is
# committed is the only way to know the page still describes the code, rather than describing
# what the code did the last time somebody remembered to regenerate it.
cp docs/index.html "$TMP/docs-committed.html"
if python3 scripts/build_docs.py >"$TMP/docs.log" 2>&1; then
  # The build stamps today's date, so that line is expected to differ and nothing else is.
  if diff <(grep -v 'built 20' "$TMP/docs-committed.html") \
          <(grep -v 'built 20' docs/index.html) >"$TMP/docs.diff" 2>&1; then
    ok "docs/index.html regenerates byte for byte from the corpus"
  else
    bad "the committed page differs from what the corpus produces"
    head -20 "$TMP/docs.diff"
  fi
  cp "$TMP/docs-committed.html" docs/index.html
else bad "the docs build failed"; cat "$TMP/docs.log"; fi

echo
if [ "$FAILED" -eq 0 ]; then echo "VERIFY OK"; else echo "VERIFY FAILED"; fi
exit "$FAILED"
