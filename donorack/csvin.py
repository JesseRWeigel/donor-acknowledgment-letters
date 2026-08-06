"""Reading a donation CSV out of whatever the charity's system exported.

THE ERROR HANDLING IS THE FEATURE. A bookkeeper runs this over 400 rows at year end. A reader that
skips bad rows silently produces 380 letters and no indication that 20 donors got nothing, and the
donors who got nothing are exactly the ones who will find out in April. So every row that cannot
be read is reported with its line number and what was wrong with it, and the caller decides
whether to proceed.

Column names are matched case-insensitively and with underscores, spaces and hyphens treated as
the same thing, because the export from one donor database calls it `Donor Name` and another calls
it `donor_name`, and failing on that would be a tool defending its own preferences.
"""
from __future__ import annotations

import csv
import dataclasses
import datetime
import io
import re

from .rules import Donation, DonationError, money, validate

# Every spelling that means the same column. The left side is what the code uses.
ALIASES = {
    "donor_name": ("donor", "name", "donorname", "contributor", "donor_full_name"),
    "date": ("donation_date", "gift_date", "received", "date_received", "contribution_date"),
    "amount": ("gift_amount", "contribution", "cash_amount", "value", "total"),
    "kind": ("type", "gift_type", "donation_type", "category"),
    "description": ("property", "item", "property_description", "gift_description"),
    "goods_value": ("benefit_value", "fmv_of_benefits", "goods_amount", "quid_pro_quo_value"),
    "goods_description": ("benefit", "benefits", "goods", "benefit_description"),
    "intangible_religious": ("religious", "intangible"),
    "vehicle_vin": ("vin",),
    "vehicle_gross_proceeds": ("gross_proceeds", "sale_proceeds"),
}

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y")
TRUE = {"1", "true", "t", "yes", "y"}
FALSE = {"0", "false", "f", "no", "n", ""}


@dataclasses.dataclass(frozen=True)
class RowError:
    line: int
    problem: str
    row: dict


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def _header_map(fieldnames) -> dict:
    """Map the file's headers onto the names the code uses."""
    lookup = {}
    for canonical, spellings in ALIASES.items():
        lookup[canonical] = canonical
        for s in spellings:
            lookup[s] = canonical
    out = {}
    for raw in fieldnames or []:
        n = _norm(raw)
        if n in lookup:
            out[raw] = lookup[n]
    return out


def parse_date(value: str) -> datetime.date:
    """A date, in any of the formats a donor database exports, or an error saying so.

    Two-digit years are read by strptime's own pivot, which puts 69 to 99 in the 1900s. A
    contribution dated 1998 is almost certainly a typo for 2098 being impossible rather than a
    genuine twenty-year-old gift, but guessing which is not this function's business, so it
    returns what the file said and `validate` elsewhere can object.
    """
    text = (value or "").strip()
    if not text:
        raise DonationError("no date; an acknowledgment has to say when the gift was received")
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise DonationError(
        f"{text!r} is not a date this recognises. Accepted: " + ", ".join(DATE_FORMATS))


def _flag(value: str) -> bool:
    text = (value or "").strip().lower()
    if text in TRUE:
        return True
    if text in FALSE:
        return False
    raise DonationError(f"{value!r} is not a yes or no")


def read_rows(text: str) -> tuple[list[Donation], list[RowError]]:
    """Donations and the rows that could not be read, both returned.

    Returning both is deliberate. A reader that raises on the first bad row makes the bookkeeper
    fix 20 typos one run at a time; a reader that returns only the good rows hides the problem.

    A row that PARSES but cannot produce a letter is reported here too, alongside the rows that
    would not parse. A non-cash gift with no description reads perfectly well as a CSV row and is
    still useless, and telling the bookkeeper about it at generation time, one row at a time,
    means several more round trips than telling them about it now with all the others.
    """
    reader = csv.DictReader(io.StringIO(text))
    mapping = _header_map(reader.fieldnames)
    missing = {"donor_name", "date", "kind"} - set(mapping.values())
    if missing:
        raise DonationError(
            f"the file has no column for {', '.join(sorted(missing))}. Headers found: "
            f"{', '.join(reader.fieldnames or ['(none)'])}")

    donations: list[Donation] = []
    errors: list[RowError] = []
    for line, raw in enumerate(reader, start=2):
        row = {mapping[k]: (v or "") for k, v in raw.items() if k in mapping}
        try:
            kind = (row.get("kind") or "cash").strip().lower().replace(" ", "-")
            if kind in ("noncash", "in-kind", "inkind", "property"):
                kind = "non-cash"
            if kind in ("car", "auto", "automobile", "boat", "airplane"):
                kind = "vehicle"
            proceeds = (row.get("vehicle_gross_proceeds") or "").strip()
            donation = Donation(
                donor_name=row.get("donor_name", "").strip(),
                date=parse_date(row.get("date", "")),
                amount=money(row.get("amount") or "0"),
                kind=kind,
                description=row.get("description", "").strip(),
                goods_value=money(row.get("goods_value") or "0"),
                goods_description=row.get("goods_description", "").strip(),
                intangible_religious=_flag(row.get("intangible_religious", "")),
                vehicle_vin=row.get("vehicle_vin", "").strip(),
                vehicle_gross_proceeds=money(proceeds) if proceeds else None,
            )
            problems = validate(donation)
            if problems:
                errors.append(RowError(line, "; ".join(problems), raw))
            else:
                donations.append(donation)
        except DonationError as e:
            errors.append(RowError(line, str(e), raw))
        except (ValueError, TypeError) as e:
            errors.append(RowError(line, f"unreadable row: {e}", raw))
    return donations, errors


def read_file(path) -> tuple[list[Donation], list[RowError]]:
    with open(path, encoding="utf-8-sig") as fh:
        return read_rows(fh.read())
