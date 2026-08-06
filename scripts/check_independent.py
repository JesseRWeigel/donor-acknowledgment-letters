"""An independent recheck of the generated letters, importing nothing from `donorack`.

The package's own auditor and its own generator could agree with each other perfectly and both be
wrong about the law. So this reads the donation CSV and the finished letters with its own parsing,
applies the substantiation rules as retyped from Publication 1771, and compares.

`verify.sh` proves the independence rather than asserting it: it walks this file's import graph
with `ast` and fails if `donorack` appears anywhere in it.

WHAT THIS CANNOT PROVE. That Publication 1771 says what both copies of the rules claim it says.
Two transcriptions by the same author share the same misreading. A lawyer reading the citations
is the check for that, and the README says so.

Usage: python3 scripts/check_independent.py <letters-dir> <donations.csv>
"""
from __future__ import annotations

import csv
import datetime
import pathlib
import re
import sys
from decimal import Decimal

# Retyped from the statute rather than imported. If someone edits the package's constants these
# have to be edited too, deliberately, which is the point.
ACK_AT_OR_ABOVE = Decimal("250")     # IRC 170(f)(8): "$250 or more"
QPQ_STRICTLY_ABOVE = Decimal("75")   # IRC 6115: "in excess of $75"

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y")
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")

failures: list[str] = []
checks = 0


def check(condition, description):
    global checks
    checks += 1
    if condition:
        print(f"    ok   {description}")
    else:
        print(f"    FAIL {description}")
        failures.append(description)


def parse_money(text):
    text = (text or "").replace("$", "").replace(",", "").strip()
    return Decimal(text) if text else Decimal("0")


def parse_date(text):
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unreadable date {text!r}")


def amounts_in(text):
    return {Decimal(m.group(1).replace(",", "")) for m in MONEY.finditer(text)}


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    letters_dir = pathlib.Path(argv[1])
    rows = list(csv.DictReader(open(argv[2], encoding="utf-8-sig")))

    print(f"  reading {len(rows)} donations and the letters in {letters_dir}")
    texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(letters_dir.glob("*.txt"))
             if not p.name.startswith(("2026-summary", "2025-summary"))}
    check(len(texts) == len(rows),
          f"one letter per donation ({len(texts)} letters, {len(rows)} rows)")

    matched = 0
    for row in rows:
        name = row["donor_name"].strip()
        date = parse_date(row["date"])
        amount = parse_money(row.get("amount"))
        goods = parse_money(row.get("goods_value"))
        kind = row["kind"].strip().lower()
        religious = (row.get("intangible_religious") or "").strip().lower() in ("yes", "y", "1",
                                                                               "true")
        # Find the letter by content rather than by filename, so a change to the naming scheme
        # does not silently make this check vacuous.
        long_date = f"{date:%B} {date.day}, {date.year}"
        found = [t for t in texts.values() if name in t and long_date in t]
        if len(found) != 1:
            check(False, f"exactly one letter for {name} on {date} (found {len(found)})")
            continue
        matched += 1
        text = found[0]
        low = text.lower()
        quid = goods > 0 and not religious

        if kind == "cash" and amount >= ACK_AT_OR_ABOVE:
            check(amount in amounts_in(text), f"{name} {date}: the letter states ${amount}")

        if quid:
            check(goods in amounts_in(text),
                  f"{name} {date}: the good faith estimate ${goods} appears")
            if amount > QPQ_STRICTLY_ABOVE:
                check(amount - goods in amounts_in(text),
                      f"{name} {date}: the deductible ${amount - goods} appears "
                      f"(${amount} paid less ${goods} received)")
            else:
                # Under the threshold the charity owes no disclosure. Volunteering one is not
                # illegal, but a tool that cannot tell the cases apart got the rule wrong.
                check("limited to the excess" not in low,
                      f"{name} {date}: no disclosure clause below the ${QPQ_STRICTLY_ABOVE} "
                      f"threshold")
        elif religious:
            check("intangible religious benefit" in low,
                  f"{name} {date}: the intangible religious benefit is stated")
        else:
            check(re.search(r"no goods or services", low) is not None,
                  f"{name} {date}: the negative statement is present")

        if kind in ("non-cash", "vehicle"):
            check(not amounts_in(text),
                  f"{name} {date}: the charity states no value for donated property")
            check(any(w in low for w in row["description"].lower().split() if len(w) > 4),
                  f"{name} {date}: the property is described")
        if kind == "vehicle":
            check("1098-c" in low, f"{name} {date}: Form 1098-C is referenced")
            check(row["vehicle_vin"].strip() in text, f"{name} {date}: the VIN appears")

    print(f"  {matched} of {len(rows)} donations matched to a letter")

    # The four-gifts case, which is the rule charities most often get backwards.
    by_donor: dict[str, list] = {}
    for row in rows:
        by_donor.setdefault(row["donor_name"].strip(), []).append(parse_money(row.get("amount")))
    for donor, gifts in by_donor.items():
        if len(gifts) > 1 and sum(gifts) >= ACK_AT_OR_ABOVE and max(gifts) < ACK_AT_OR_ABOVE:
            print(f"  {donor} gave {len(gifts)} gifts totalling ${sum(gifts)}, none at or above "
                  f"${ACK_AT_OR_ABOVE}")
            break
    else:
        check(False, "the corpus contains a donor whose gifts total over $250 with no single "
                     "gift over $250, which is the case the per-contribution rule exists for")

    check_widths()

    print(f"  {checks} independent checks, {len(failures)} failed")
    for f in failures:
        print(f"    {f}")
    return 1 if failures else 0


def check_widths():
    """Compare the shipped Helvetica table against the AFM copy inside pdfminer.

    Read as text and parsed here rather than imported, so this file's import graph stays free of
    the package under test. What it proves: the shipped table matches Adobe's published metrics as
    a third party distributes them. What it does not prove: that Adobe is right.
    """
    try:
        from pdfminer.fontmetrics import FONT_METRICS
    except ImportError:
        check(False, "pdfminer.six is needed to check the font metrics independently")
        return

    source = pathlib.Path("donorack/pdfwrite.py").read_text(encoding="utf-8")
    for name, face in (("HELVETICA", "Helvetica"), ("HELVETICA_BOLD", "Helvetica-Bold")):
        block = source.split(f"{name} = {{", 1)[1].split("}", 1)[0]
        shipped = {int(k): int(v) for k, v in re.findall(r"(\d+):\s*(\d+)", block)}
        _, reference = FONT_METRICS[face]
        expected = {ord(ch): int(w) for ch, w in reference.items()
                    if len(ch) == 1 and ord(ch) < 256}
        check(shipped == expected,
              f"{face}: all {len(expected)} widths match the AFM metrics in pdfminer "
              f"({len(set(shipped.items()) ^ set(expected.items()))} differences)")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
