"""The substantiation rules, encoded from IRS Publication 1771 and the sections behind it.

A donor acknowledgment letter is a legal instrument. If it is missing a required sentence the
donor's deduction can be disallowed on audit, and the person who loses is the donor, years later,
with no way to go back and get a corrected letter because the rule requires it to be
contemporaneous. Small charities send letters that would not survive that, and they send them in
good faith, because the requirements are counterintuitive.

THE TWO THRESHOLDS ARE DIFFERENT RULES AND THEY ARE CONSTANTLY CONFLATED.

  $250   Section 170(f)(8). Above this, the DONOR may not deduct without a contemporaneous
         written acknowledgment from the charity. The duty this creates is the donor's; the
         charity's letter is what makes the deduction possible. Applies per contribution, not
         to the annual total, which is why four $100 gifts need no letter and one $400 gift does.

  $75    Section 6115. Above this, on a QUID PRO QUO contribution, the CHARITY must disclose in
         writing that only the amount above the value of goods received is deductible, and must
         give a good faith estimate of that value. This is a penalty on the charity, not on the
         donor, and it applies at $75 whether or not the $250 rule is in play.

So a $100 gala ticket where the dinner is worth $40 requires a disclosure even though it is under
$250, and a $300 cash gift requires an acknowledgment even though nothing was received in return.
Both, neither, or one can apply to the same gift.

THE SENTENCE THAT MATTERS MOST IS A NEGATIVE. A letter for a straightforward $500 cash gift must
say that no goods or services were provided in exchange. Its absence is the single most common
defect, because the drafter has nothing to report and so reports nothing.

WHAT A CHARITY MUST NOT DO. It must not state the value of non-cash property. Valuation is the
donor's responsibility and appraisal is a regulated activity; a charity that helpfully writes
"thank you for your car, valued at $4,000" has given the donor a figure they did not appraise and
has stepped into a role the rules assign elsewhere. This describes the property and refuses to
price it.

Every rule here carries the citation it comes from, so a reader can check it rather than trust it.
None of this is legal advice, and `verify.sh` checks that disclaimer is present.
"""
from __future__ import annotations

import dataclasses
import datetime
import decimal
from decimal import Decimal

decimal.getcontext().prec = 12

# Section 170(f)(8): written acknowledgment required for the donor to deduct.
ACKNOWLEDGMENT_THRESHOLD = Decimal("250.00")
# Section 6115: quid pro quo disclosure required of the charity.
QUID_PRO_QUO_THRESHOLD = Decimal("75.00")
# Section 170(f)(12): vehicle donations have their own regime and Form 1098-C.
VEHICLE_FORM = "1098-C"

CITATIONS = {
    "acknowledgment": "IRC 170(f)(8); IRS Publication 1771, page 2",
    "quid_pro_quo": "IRC 6115; IRS Publication 1771, page 5",
    "no_goods_statement": "IRS Publication 1771, page 3",
    "no_valuation": "IRS Publication 1771, page 3; Treas. Reg. 1.170A-13(c)",
    "vehicle": "IRC 170(f)(12); IRS Publication 4302",
    "contemporaneous": "IRC 170(f)(8)(C)",
    "intangible_religious": "IRC 170(f)(8)(B)(iii)",
}


class DonationError(ValueError):
    pass


def money(value) -> Decimal:
    """A currency amount, refused rather than rounded if it is not one.

    Decimal throughout. Float arithmetic on money produces 74.99999999999999 against a $75.00
    threshold, and a disclosure that fires or does not fire on a floating point artefact is a
    legal defect rather than a rounding cosmetic.
    """
    if value is None or value == "":
        raise DonationError("an amount is required")
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (decimal.InvalidOperation, AttributeError) as e:
        raise DonationError(f"{value!r} is not an amount") from e
    if amount < 0:
        raise DonationError(f"a contribution cannot be negative: {amount}")
    return amount.quantize(Decimal("0.01"))


@dataclasses.dataclass(frozen=True)
class Donation:
    donor_name: str
    date: datetime.date
    amount: Decimal                       # cash paid, or 0 for a pure non-cash gift
    kind: str                             # cash | non-cash | vehicle
    description: str = ""                 # required for non-cash; never a value
    goods_value: Decimal = Decimal("0")   # good faith estimate of what the donor received
    goods_description: str = ""
    intangible_religious: bool = False
    vehicle_vin: str = ""
    vehicle_gross_proceeds: Decimal | None = None

    @property
    def deductible(self) -> Decimal:
        """Cash paid less the value of what the donor got back. Never below zero."""
        return max(Decimal("0"), self.amount - self.goods_value)

    @property
    def is_quid_pro_quo(self) -> bool:
        """Did the donor receive something? Token items and intangible religious benefits do not
        count under the statute, and the caller marks those explicitly."""
        return self.goods_value > 0 and not self.intangible_religious


@dataclasses.dataclass(frozen=True)
class Requirement:
    rule: str
    citation: str
    required: bool
    reason: str


def requirements(donation: Donation) -> list[Requirement]:
    """Every rule that applies to this gift, with why it does or does not.

    Returns the negative cases too. A charity deciding whether it needs a letter is served by
    "not required, because this contribution is under $250 and nothing was received in return"
    far better than by silence, which is indistinguishable from the tool not having looked.
    """
    out: list[Requirement] = []

    needs_ack = donation.amount >= ACKNOWLEDGMENT_THRESHOLD
    out.append(Requirement(
        "written acknowledgment", CITATIONS["acknowledgment"], needs_ack,
        f"the contribution is {'at or above' if needs_ack else 'below'} the "
        f"${ACKNOWLEDGMENT_THRESHOLD} threshold, so the donor "
        f"{'cannot deduct it without a written acknowledgment' if needs_ack else 'may substantiate it with a bank record'}"))

    needs_qpq = donation.is_quid_pro_quo and donation.amount > QUID_PRO_QUO_THRESHOLD
    if donation.intangible_religious and donation.goods_value > 0:
        reason = ("the only benefit was an intangible religious one, which the statute excludes "
                  "from the quid pro quo rules")
    elif not donation.is_quid_pro_quo:
        reason = "nothing of value was provided in return"
    elif not needs_qpq:
        reason = (f"the payment of ${donation.amount} does not exceed the "
                  f"${QUID_PRO_QUO_THRESHOLD} threshold")
    else:
        reason = (f"the donor paid ${donation.amount} and received goods worth "
                  f"${donation.goods_value}, so the charity must state that only "
                  f"${donation.deductible} is deductible")
    out.append(Requirement("quid pro quo disclosure", CITATIONS["quid_pro_quo"],
                           needs_qpq, reason))

    if needs_ack or donation.kind != "cash":
        out.append(Requirement(
            "statement about goods and services", CITATIONS["no_goods_statement"], True,
            "every acknowledgment must state either that no goods or services were provided, or "
            "describe what was and estimate its value. Omitting the negative statement is the "
            "most common defect in letters that fail an audit"))

    if donation.kind == "non-cash":
        out.append(Requirement(
            "describe the property without valuing it", CITATIONS["no_valuation"], True,
            "the charity describes what it received; the donor determines value. A charity that "
            "states a value has taken on a role the regulations assign to the donor and, above "
            "$5,000, to a qualified appraiser"))

    if donation.kind == "vehicle":
        out.append(Requirement(
            f"Form {VEHICLE_FORM}", CITATIONS["vehicle"], True,
            "vehicle donations are governed separately. The charity must furnish Form 1098-C and "
            "the deduction is generally limited to the gross proceeds of sale, so a letter alone "
            "does not substantiate it"))

    return out


def validate(donation: Donation) -> list[str]:
    """Problems that stop a correct letter being written, stated rather than papered over."""
    problems = []
    if not donation.donor_name.strip():
        problems.append("the donor's name is missing, and an acknowledgment must identify them")
    if donation.kind not in ("cash", "non-cash", "vehicle"):
        problems.append(f"{donation.kind!r} is not a kind of donation this handles")
    if donation.kind in ("non-cash", "vehicle") and not donation.description.strip():
        problems.append("a non-cash gift must be described, and no letter can be written without "
                        "knowing what was received")
    if donation.goods_value > 0 and not donation.goods_description.strip():
        problems.append("goods were valued but not described, and the disclosure has to say what "
                        "the donor received")
    if donation.goods_value > donation.amount and donation.kind == "cash":
        problems.append(f"the goods provided (${donation.goods_value}) are worth more than the "
                        f"payment (${donation.amount}), so this is a purchase rather than a "
                        f"contribution and no part of it is deductible")
    if donation.kind == "vehicle" and not donation.vehicle_vin.strip():
        problems.append("a vehicle donation needs its VIN, which Form 1098-C requires")
    return problems


def deadline(donation: Donation, filing_deadline: datetime.date | None = None) -> datetime.date:
    """When the acknowledgment stops being contemporaneous and therefore stops working.

    The rule is the earlier of the date the donor files, or the due date including extensions.
    A charity cannot know when its donor filed, so this reports the statutory due date and the
    letter says plainly that a later letter may not help.
    """
    if filing_deadline:
        return filing_deadline
    return datetime.date(donation.date.year + 1, 4, 15)
