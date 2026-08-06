"""Composing the letter, with the required sentences present because they are checked for.

The letter is assembled from named clauses rather than a single template string, so that
`audit.py` can inspect a finished letter and say which required clauses are present and which are
missing. A template makes the right letter by construction and gives you no way to prove it did.

WHAT MUST APPEAR, and every one of these is checked after the letter is written:

  the charity's name
  the donation date
  the amount, for cash
  a description of the property, for non-cash, WITHOUT a value
  either "no goods or services were provided" or a description and good faith estimate
  for quid pro quo over $75, the deductible amount stated explicitly

WHAT MUST NOT APPEAR:

  a dollar value attached to donated property
  a claim that the whole payment is deductible when goods were received
  tax advice

The wording follows the sample language in Publication 1771 closely. This is one of the few
places where paraphrasing is worse than copying, because the phrases are what an examiner looks
for and a fluent rewrite loses the thing that makes the letter work.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from .rules import (QUID_PRO_QUO_THRESHOLD, Donation, deadline, money,  # noqa: F401
                    requirements, validate)

DISCLAIMER = ("This letter is generated from the substantiation rules in IRS Publication 1771. "
              "It is not tax or legal advice, and a charity relying on it should have its "
              "template reviewed by its own counsel.")


@dataclasses.dataclass(frozen=True)
class Charity:
    name: str
    ein: str
    address: str
    signatory: str = ""
    signatory_title: str = ""

    def validate(self) -> list[str]:
        problems = []
        if not self.name.strip():
            problems.append("the charity's name is required and is the point of the letter")
        digits = self.ein.replace("-", "").strip()
        if not (len(digits) == 9 and digits.isdigit()):
            problems.append(f"{self.ein!r} is not an EIN; the format is 00-1234567")
        if not self.address.strip():
            problems.append("an address is required")
        return problems


@dataclasses.dataclass(frozen=True)
class Clause:
    name: str
    text: str
    required: bool


def clauses(charity: Charity, donation: Donation) -> list[Clause]:
    """The letter as named parts, so the finished thing can be audited rather than trusted."""
    out: list[Clause] = []
    when = donation.date.strftime("%B %-d, %Y") if hasattr(donation.date, "strftime") else str(donation.date)

    out.append(Clause("salutation", f"Dear {donation.donor_name},", True))

    if donation.kind == "cash":
        out.append(Clause(
            "receipt",
            f"Thank you for your contribution of ${donation.amount:,.2f} received on {when}.",
            True))
    else:
        out.append(Clause(
            "receipt",
            f"Thank you for your contribution of the following property, received on {when}: "
            f"{donation.description}.",
            True))
        # Deliberately separate, because the omission is the point rather than an oversight.
        out.append(Clause(
            "no-valuation",
            "This letter describes what was received. It does not state a value, because "
            "determining the value of donated property is the donor's responsibility.",
            True))

    if donation.is_quid_pro_quo:
        out.append(Clause(
            "goods-provided",
            f"In return for this contribution you received {donation.goods_description}, for "
            f"which we make a good faith estimate of value of ${donation.goods_value:,.2f}.",
            True))
        if donation.amount > QUID_PRO_QUO_THRESHOLD:
            out.append(Clause(
                "deductible-amount",
                f"Under the Internal Revenue Code, the amount of your contribution that is "
                f"deductible for federal income tax purposes is limited to the excess of the "
                f"amount contributed over the value of the goods or services provided. That "
                f"amount is ${donation.deductible:,.2f}.",
                True))
    elif donation.intangible_religious:
        out.append(Clause(
            "intangible-religious",
            "The only benefit you received was an intangible religious benefit, which is not "
            "treated as goods or services for this purpose.",
            True))
    else:
        # The single most commonly omitted sentence in the whole letter.
        out.append(Clause(
            "no-goods-statement",
            "No goods or services were provided to you in exchange for this contribution.",
            True))

    if donation.kind == "vehicle":
        out.append(Clause(
            "vehicle",
            f"This vehicle donation (VIN {donation.vehicle_vin}) is also reported to you and to "
            f"the Internal Revenue Service on Form 1098-C. Your deduction is generally limited "
            f"to the gross proceeds from our sale of the vehicle, and this letter alone does not "
            f"substantiate it.",
            True))

    out.append(Clause(
        "charity-identity",
        f"{charity.name} is a tax-exempt organization. Our EIN is {charity.ein}. "
        f"{charity.address}",
        True))

    out.append(Clause(
        "contemporaneous",
        f"Please keep this letter with your tax records. To support a deduction it must be in "
        f"your hands by the earlier of the date you file your return or its due date, which for "
        f"a {donation.date.year} contribution is generally "
        f"{deadline(donation).strftime('%B %-d, %Y')}.",
        True))

    if charity.signatory:
        title = f", {charity.signatory_title}" if charity.signatory_title else ""
        out.append(Clause("signature", f"With thanks,\n{charity.signatory}{title}\n{charity.name}",
                          False))
    return out


def compose(charity: Charity, donation: Donation) -> str:
    """The finished letter. Raises rather than producing a defective one."""
    problems = charity.validate() + validate(donation)
    if problems:
        raise ValueError("; ".join(problems))
    body = "\n\n".join(c.text for c in clauses(charity, donation))
    return body + "\n\n---\n" + DISCLAIMER + "\n"


def year_end_summary(charity: Charity, donor_name: str,
                     donations: list[Donation], year: int) -> str:
    """A year-end statement, which is a convenience and NOT a substitute for the letters.

    The rule is per contribution. A donor who gave $300 once needs an acknowledgment for that
    gift, and a summary listing it among others does not become the contemporaneous written
    acknowledgment for it unless it carries the same required language. So this repeats the
    goods-and-services statement per line rather than once at the bottom, and says plainly what
    it is not.
    """
    rows = sorted((d for d in donations if d.date.year == year), key=lambda d: d.date)
    total = sum((d.amount for d in rows), Decimal("0"))
    deductible = sum((d.deductible for d in rows), Decimal("0"))
    lines = [f"{charity.name}", f"EIN {charity.ein}", "",
             f"Summary of {year} contributions for {donor_name}", ""]
    for d in rows:
        when = d.date.strftime("%b %-d")
        if d.kind == "cash":
            item = f"  {when}   ${d.amount:>10,.2f}"
        else:
            item = f"  {when}   {d.description}"
        if d.is_quid_pro_quo:
            item += (f"   goods received: {d.goods_description} "
                     f"(${d.goods_value:,.2f}); deductible ${d.deductible:,.2f}")
        else:
            item += "   no goods or services were provided in exchange"
        lines.append(item)
    lines += ["",
              f"  Total contributed   ${total:,.2f}",
              f"  Total deductible    ${deductible:,.2f}",
              "",
              "This summary is provided for your convenience. The Internal Revenue Code requires "
              "a separate written acknowledgment for each contribution of $250 or more, and this "
              "summary does not replace those letters.",
              "", "---", DISCLAIMER]
    return "\n".join(lines) + "\n"
