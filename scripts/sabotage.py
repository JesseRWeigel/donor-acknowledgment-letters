"""Break the code on purpose and confirm something notices.

THE THREE GATES. A sabotage counts only if all three hold:

  1. it APPLIES, meaning the edit actually changed the file
  2. it CHANGES THE MEASURED OUTPUT, meaning the letters, the rules report or the audit result
     differ from the clean run
  3. and only then, it is CAUGHT by the checks

Gate 2 is the one that gets skipped, and skipping it is how a test suite acquires a reputation it
has not earned. A sabotage that edits a branch nothing reaches proves that the checks did not
notice a change that never happened. Here it is a failure, reported as `NO-OP`, not a pass.

GUARD SABOTAGES INVERT GATE 2. Some code is dormant when everything is correct: the auditor finds
nothing wrong with a correct letter, so disabling the auditor changes no letter. For those the
requirement is the opposite, and it is stricter: the measured output must be UNCHANGED and the
unit suite must FAIL. A guard sabotage that changes the letters is also a failure, because it
means the thing being disabled was not a guard.

Usage:
  python3 scripts/sabotage.py --list
  python3 scripts/sabotage.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]

# (name, file, find, replace, kind, what should catch it)
SABOTAGES = [
    ("ack-threshold-off-by-one", "donorack/rules.py",
     'ACKNOWLEDGMENT_THRESHOLD = Decimal("250.00")',
     'ACKNOWLEDGMENT_THRESHOLD = Decimal("251.00")',
     "attack", "the $250 boundary tests"),

    ("qpq-threshold-inclusive", "donorack/letter.py",
     "if donation.amount > QUID_PRO_QUO_THRESHOLD:",
     "if donation.amount >= QUID_PRO_QUO_THRESHOLD:",
     "attack", "the independent check that a $75 gift gets no disclosure clause"),

    ("deductible-ignores-goods", "donorack/rules.py",
     'return max(Decimal("0"), self.amount - self.goods_value)',
     "return self.amount",
     "attack", "the independent recomputation of the deductible amount"),

    ("drop-the-negative-statement", "donorack/letter.py",
     '"No goods or services were provided to you in exchange for this contribution.",',
     '"Thank you again for your support of our work.",',
     "attack", "the auditor and the independent checker"),

    ("charity-values-the-property", "donorack/letter.py",
     '"This letter describes what was received. It does not state a value, because "',
     '"This letter describes what was received, with a fair market value of $500.00, because "',
     "attack", "the no-valuation rule"),

    ("summary-poses-as-an-acknowledgment", "donorack/letter.py",
     '"summary does not replace those letters.",',
     '"summary serves as your acknowledgment for each of them.",',
     "attack", "the year-end summary tests"),

    ("csv-swallows-bad-rows", "donorack/csvin.py",
     "errors.append(RowError(line, str(e), raw))",
     "pass",
     "attack", "the row-level error reporting tests"),

    ("width-table-typo", "donorack/pdfwrite.py",
     "101: 556, 102: 278,",
     "101: 500, 102: 278,",
     "attack", "the width comparison against pdfminer's AFM metrics"),

    ("fixed-character-width", "donorack/pdfwrite.py",
     "        total += w",
     "        total += 500",
     "attack", "the proportional-width tests"),

    ("pdf-escaping-off", "donorack/pdfwrite.py",
     '    for a, b in ((b"\\\\", b"\\\\\\\\"), (b"(", b"\\\\("), (b")", b"\\\\)")):',
     "    for a, b in ():",
     "attack", "the awkward-description letters, whose text has an unclosed parenthesis"),

    # A false-positive sabotage. The auditor's job includes NOT flagging correct letters, and a
    # checker that cries wolf gets switched off, which is the same as having no checker.
    ("auditor-cries-wolf", "donorack/audit.py",
     "        stated = {Decimal(m.group(1).replace(\",\", \"\")) for m in MONEY.finditer(text)}\n"
     "        check(DEDUCTIBLE_WORD.search(text) is not None and donation.deductible in stated,",
     "        near = re.compile(r\"deductible[^.]{0,120}?\\$\", re.I)\n"
     "        check(near.search(text) is not None,",
     "attack", "the audit of correct letters, which must stay clean"),

    # Guard sabotages: dormant on correct input, so the letters must NOT change and the unit
    # suite must fail.
    ("auditor-finds-nothing", "donorack/audit.py",
     "        checks += 1\n        if not condition:",
     "        checks += 1\n        if False:",
     "attack_guard", "the auditor's own defect tests"),

    ("validate-accepts-everything", "donorack/rules.py",
     "    problems = []\n    if not donation.donor_name.strip():",
     "    problems = []\n    if False:",
     "attack", "the validation tests and the problem-row report"),

    ("encoding-error-suppressed", "donorack/pdfwrite.py",
     '        if w is None:\n            raise PdfEncodingError(',
     '        if w is None:\n            w = 500\n        if False:\n            raise '
     'PdfEncodingError(',
     "attack_guard", "the test that an unmetricked character raises"),
]


def measure(work: pathlib.Path) -> str:
    """A fingerprint of everything the tool produces on the corpus.

    The letters, the summaries, the rules report and the audit result, all of it. If a change to
    the code moves any of them, this string moves. That is what gate 2 tests.

    IT MUST NOT MOVE FOR ANY OTHER REASON. Each sabotage runs in its own temporary copy of the
    tree, so anything carrying the working directory into the output makes every fingerprint
    unique and gate 2 passes for every sabotage whether or not it changed anything. The first
    version of this function did exactly that, by way of the `letters written to <out>` line, and
    the eleven sabotages it scored as proven were proving nothing. Hence the relative paths below
    and the scrub afterwards.
    """
    out = work / "_measure"
    shutil.rmtree(out, ignore_errors=True)
    blob = {}
    for args in (["letters", "--csv", "corpus/donations.csv", "--charity", "corpus/charity.json",
                  "--out", "_measure", "--no-pdf"],
                 ["summaries", "--csv", "corpus/donations.csv", "--charity",
                  "corpus/charity.json", "--out", "_measure", "--no-pdf", "--year", "2026"],
                 ["rules", "--csv", "corpus/donations.csv"],
                 ["rules", "--csv", "corpus/problem-rows.csv"],
                 # Descriptions a bookkeeper really types: an unclosed parenthesis and an inch
                 # mark. Both are legal in a letter and both break a PDF string that is not
                 # escaped, so without this fixture the escaping is never exercised and a
                 # sabotage against it is a no-op.
                 ["letters", "--csv", "corpus/awkward.csv", "--charity", "corpus/charity.json",
                  "--out", "_awkward"]):
        r = subprocess.run([sys.executable, "-m", "donorack.cli", *args], cwd=work,
                           capture_output=True, text=True)
        blob[args[0] + str(args[2:4])] = [r.returncode, r.stdout, r.stderr]

    if out.exists():
        for path in sorted(out.iterdir()):
            blob[path.name] = path.read_text(encoding="utf-8", errors="replace")

    # The PDF path, separately, so a break there is visible even though the text is fine.
    pdf_out = work / "_measure_pdf"
    shutil.rmtree(pdf_out, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "donorack.cli", "letters", "--csv",
                    "corpus/donations.csv", "--charity", "corpus/charity.json", "--out",
                    "_measure_pdf"], cwd=work, capture_output=True, text=True)
    if pdf_out.exists():
        for path in sorted(pdf_out.glob("*.pdf")):
            blob["pdf:" + path.name] = extract(path)
    for path in sorted((work / "_awkward").glob("*.pdf")):
        blob["awkward:" + path.name] = extract(path)

    text = json.dumps(blob, sort_keys=True)
    for path in (str(work), str(work.resolve())):
        text = text.replace(path, "<work>")
    return hashlib.sha256(text.encode()).hexdigest()


def extract(path: pathlib.Path) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(path))
    except Exception as e:                      # a broken PDF is itself a measurable difference
        return f"unreadable: {type(e).__name__}"


def caught(work: pathlib.Path) -> tuple[bool, str]:
    """Do the project's own checks notice? Unit suite first, then the independent checker."""
    unit = subprocess.run(UNIT, cwd=work, capture_output=True, text=True)
    if unit.returncode != 0:
        first = [ln for ln in unit.stderr.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
        return True, f"unit suite: {first[0] if first else 'failed'}"

    out = work / "_ind"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "donorack.cli", "letters", "--csv",
                    "corpus/donations.csv", "--charity", "corpus/charity.json", "--out",
                    str(out), "--no-pdf"], cwd=work, capture_output=True, text=True)
    ind = subprocess.run([sys.executable, "scripts/check_independent.py", str(out),
                          "corpus/donations.csv"], cwd=work, capture_output=True, text=True)
    if ind.returncode != 0:
        first = [ln.strip() for ln in ind.stdout.splitlines() if ln.strip().startswith("FAIL")]
        return True, f"independent checker: {first[0] if first else 'failed'}"
    return False, "nothing noticed"


def run_one(name, relpath, find, replace, kind, catcher, baseline, tmp) -> tuple[str, str]:
    work = pathlib.Path(tmp) / name
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "out", "_measure*", "_awkward", "_ind", "docs"))
    target = work / relpath
    before = target.read_text(encoding="utf-8")
    if find not in before:
        return "NOT-FOUND", f"the text to replace is not in {relpath}"
    target.write_text(before.replace(find, replace, 1), encoding="utf-8")
    if target.read_text(encoding="utf-8") == before:
        return "NO-OP", "the edit did not change the file"

    after = measure(work)
    changed = after != baseline
    was_caught, how = caught(work)

    if kind == "attack_guard":
        if changed:
            return "NOT-A-GUARD", ("the measured output changed, so this is not dormant code and "
                                   "should be run as a plain attack")
        if not was_caught:
            return "MISSED", f"output unchanged as expected, but nothing failed ({catcher})"
        return "CAUGHT", f"output unchanged (guard), {how}"

    if not changed:
        return "NO-OP", ("the edit applied but the letters, the reports and the exit codes are "
                         "byte for byte identical, so catching it would prove nothing")
    if not was_caught:
        return "MISSED", f"output changed and nothing failed; expected {catcher}"
    return "CAUGHT", how


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--list", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--only")
    args = p.parse_args(argv)

    if args.list:
        for name, relpath, _, _, kind, catcher in SABOTAGES:
            print(f"  {name:34s} {kind:13s} {relpath:22s} caught by {catcher}")
        return 0

    selected = [s for s in SABOTAGES if not args.only or s[0] == args.only]
    if not selected:
        print(f"no sabotage named {args.only}")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        clean = pathlib.Path(tmp) / "_clean"
        shutil.copytree(ROOT, clean, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "out", "_measure*", "_awkward", "_ind", "docs"))
        baseline = measure(clean)
        print(f"  baseline fingerprint {baseline[:16]}")

        # The null control, and it runs first because everything below is void without it. A
        # second untouched copy in a different directory must fingerprint identically. If it does
        # not, the measurement is picking up the working directory rather than the code, gate 2
        # is satisfied by every sabotage automatically, and the whole run means nothing.
        null = pathlib.Path(tmp) / "_null"
        shutil.copytree(ROOT, null, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "out", "_measure*", "_awkward", "_ind", "docs"))
        control = measure(null)
        if control != baseline:
            print(f"  BROKEN HARNESS: an unmodified copy fingerprints {control[:16]}, not "
                  f"{baseline[:16]}. The measurement is not a function of the code alone, so "
                  f"gate 2 cannot distinguish a real change from a no-op.")
            return 2
        print(f"  null control     {control[:16]} matches, so the fingerprint tracks the code")

        results = []
        for s in selected:
            verdict, detail = run_one(*s, baseline=baseline, tmp=tmp)
            results.append((s[0], verdict, detail))
            print(f"  {verdict:12s} {s[0]:34s} {detail}")

    bad = [r for r in results if r[1] != "CAUGHT"]
    print(f"\n  {len(results) - len(bad)}/{len(results)} sabotages proven")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
