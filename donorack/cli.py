"""The command line.

Four things a charity actually does:

  letters      generate acknowledgments from a donation CSV, as text and PDF
  summaries    generate year-end statements per donor
  audit        read letters the charity already sent and say which would not survive
  rules        explain, per donation, which requirements apply and why

EVERY GENERATED LETTER IS AUDITED BEFORE IT IS WRITTEN OUT, and the exit code reflects it. A
generator that reports success for a letter missing a required sentence is worse than no tool,
because the charity now believes it is covered. If the auditor finds a defect the file is still
written, so a human can look at it, and the command exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .audit import audit_letter
from .csvin import read_file
from .letter import Charity, compose, year_end_summary
from .pdfwrite import PdfEncodingError, letter_pdf
from .rules import DonationError, requirements


def load_charity(path) -> Charity:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    known = {f: data[f] for f in ("name", "ein", "address", "signatory", "signatory_title")
             if f in data}
    charity = Charity(**known)
    problems = charity.validate()
    if problems:
        raise DonationError(f"{path}: " + "; ".join(problems))
    return charity


def _slug(name: str, date) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"{date.isoformat()}-{safe or 'donor'}"


def cmd_letters(args) -> int:
    charity = load_charity(args.charity)
    donations, errors = read_file(args.csv)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    written, defective, refused = 0, 0, 0
    for d in donations:
        try:
            text = compose(charity, d)
        except DonationError as e:
            refused += 1
            print(f"  refused  {d.donor_name} {d.date}: {e}", file=sys.stderr)
            continue
        except ValueError as e:
            refused += 1
            print(f"  refused  {d.donor_name} {d.date}: {e}", file=sys.stderr)
            continue

        stem = out / _slug(d.donor_name, d.date)
        stem.with_suffix(".txt").write_text(text, encoding="utf-8")
        if not args.no_pdf:
            try:
                stem.with_suffix(".pdf").write_bytes(
                    letter_pdf(text, title=f"Acknowledgment for {d.donor_name}"))
            except PdfEncodingError as e:
                refused += 1
                print(f"  no pdf   {d.donor_name}: {e}", file=sys.stderr)

        result = audit_letter(text, d, charity.name, charity.ein)
        written += 1
        if not result.passes:
            defective += 1
            print(f"  DEFECT   {stem.name}", file=sys.stderr)
            for f in result.findings:
                print(f"             {f.severity}: {f.rule} [{f.citation}]", file=sys.stderr)

    for e in errors:
        print(f"  row {e.line}: {e.problem}", file=sys.stderr)

    print(f"{written} letters written to {out}")
    if errors:
        print(f"{len(errors)} rows could not be read")
    if refused:
        print(f"{refused} donations refused")
    if defective:
        print(f"{defective} letters have defects")
    return 1 if (errors or defective or refused) else 0


def cmd_summaries(args) -> int:
    charity = load_charity(args.charity)
    donations, errors = read_file(args.csv)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    by_donor: dict[str, list] = {}
    for d in donations:
        if d.date.year == args.year:
            by_donor.setdefault(d.donor_name, []).append(d)

    for donor, rows in sorted(by_donor.items()):
        text = year_end_summary(charity, donor, rows, args.year)
        stem = out / f"{args.year}-summary-{_slug(donor, rows[0].date).split('-', 3)[-1]}"
        stem.with_suffix(".txt").write_text(text, encoding="utf-8")
        if not args.no_pdf:
            stem.with_suffix(".pdf").write_bytes(
                letter_pdf(text, title=f"{args.year} summary for {donor}"))

    print(f"{len(by_donor)} summaries for {args.year} written to {out}")
    for e in errors:
        print(f"  row {e.line}: {e.problem}", file=sys.stderr)
    return 1 if errors else 0


def cmd_rules(args) -> int:
    donations, errors = read_file(args.csv)
    for d in donations:
        print(f"{d.date}  {d.donor_name}  ${d.amount} {d.kind}")
        for r in requirements(d):
            mark = "REQUIRED" if r.required else "not req "
            print(f"    {mark}  {r.rule}")
            print(f"              {r.reason}")
            print(f"              {r.citation}")
    for e in errors:
        print(f"  row {e.line}: {e.problem}", file=sys.stderr)
    return 1 if errors else 0


def cmd_audit(args) -> int:
    """Audit letters the charity already has, which is the reason to run this at all."""
    charity = load_charity(args.charity) if args.charity else None
    donations, errors = read_file(args.csv)

    failed = 0
    checked = 0
    for path in sorted(pathlib.Path(p) for p in args.letters):
        text = read_any(path)
        candidates = match_donation(text, donations)
        if len(candidates) != 1:
            # Guessing here is worse than refusing. A donor who gave twice gets two letters with
            # different requirements, and checking the September letter against the March gift
            # reports defects that are not in the letter at all.
            failed += 1
            if not candidates:
                print(f"{path.name}: no donation in the CSV matches both a donor name and a date "
                      f"this letter mentions, so there is nothing to check it against",
                      file=sys.stderr)
            else:
                print(f"{path.name}: {len(candidates)} donations match this letter "
                      f"({', '.join(f'{d.date} ${d.amount}' for d in candidates)}), so which set "
                      f"of requirements applies is ambiguous", file=sys.stderr)
            continue
        match = candidates[0]
        result = audit_letter(text, match, charity.name if charity else "",
                              charity.ein if charity else "")
        checked += 1
        status = "ok" if result.passes else "DEFECTIVE"
        print(f"{path.name}: {status} ({result.checks_run} checks)")
        for f in result.findings:
            print(f"    {f.severity}: {f.rule}")
            print(f"      {f.detail}")
            print(f"      {f.citation}")
        if not result.passes:
            failed += 1

    print(f"{checked} letters checked, {failed} with defects")
    for e in errors:
        print(f"  row {e.line}: {e.problem}", file=sys.stderr)
    return 1 if failed or errors else 0


def match_donation(text: str, donations) -> list:
    """Which donations this letter could be about, on the donor's name AND the date.

    Name alone is not enough. A donor who gives twice in a year gets two letters whose
    requirements differ, and the tool has no business deciding which one it is looking at. So
    both have to appear, and an ambiguous result is returned as ambiguous rather than resolved.

    Dates are matched in the long form the letter writes and in ISO, because a charity auditing
    its own back catalogue is feeding in letters this tool did not write.
    """
    low = text.lower()
    out = []
    for d in donations:
        if d.donor_name.lower() not in low:
            continue
        forms = {d.date.isoformat(),
                 d.date.strftime("%B %-d, %Y").lower(),
                 d.date.strftime("%b %-d, %Y").lower(),
                 d.date.strftime("%-m/%-d/%Y")}
        if any(f in low for f in forms):
            out.append(d)
    return out


def read_any(path: pathlib.Path) -> str:
    """Letter text, from a .txt or from a PDF.

    PDF reading needs pdfminer, which is a verification dependency rather than a runtime one, so
    the import is here and the error says what to install instead of a bare ImportError.
    """
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8")
    try:
        from pdfminer.high_level import extract_text
    except ImportError as e:
        raise DonationError(
            f"reading {path.name} needs pdfminer.six (pip install pdfminer.six). Generating "
            f"letters needs nothing beyond the standard library; only reading PDFs back does."
        ) from e
    return extract_text(str(path))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="donorack", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--csv", required=True, help="donation CSV")
        sp.add_argument("--charity", help="charity JSON: name, ein, address, signatory")
        sp.add_argument("--out", default="out", help="output directory")
        sp.add_argument("--no-pdf", action="store_true", help="text only")

    letters = sub.add_parser("letters", help="generate acknowledgment letters")
    common(letters)
    letters.set_defaults(func=cmd_letters)

    summaries = sub.add_parser("summaries", help="generate year-end statements")
    common(summaries)
    summaries.add_argument("--year", type=int, required=True)
    summaries.set_defaults(func=cmd_summaries)

    rules = sub.add_parser("rules", help="explain which requirements apply and why")
    rules.add_argument("--csv", required=True)
    rules.set_defaults(func=cmd_rules)

    audit = sub.add_parser("audit", help="check letters that already exist")
    audit.add_argument("letters", nargs="+")
    audit.add_argument("--csv", required=True)
    audit.add_argument("--charity")
    audit.set_defaults(func=cmd_audit)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "charity", None) is None and args.command in ("letters", "summaries"):
        print("--charity is required to write a letter; the letter has to name the "
              "organisation", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except DonationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
