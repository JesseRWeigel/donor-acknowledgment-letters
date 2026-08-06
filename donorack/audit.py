"""Reading a finished letter and saying whether it carries what the rules require.

This is the part worth having. Generating a correct letter is useful once; auditing the letters a
charity is already sending tells them whether the last three years of acknowledgments would
survive, and that is the question they actually have.

It works on TEXT, not on the objects that produced it. Checking the generator's own data
structures would confirm the generator agrees with itself. Reading the letter is what a examiner
does, so it is what this does, and it means the same auditor works on a letter written in Word by
somebody who has never seen this tool.

THE FINDINGS ARE ORDERED BY CONSEQUENCE, not by position in the document. A missing goods and
services statement can cost the donor the entire deduction. A missing EIN is untidy. Presenting
them as a flat list of problems invites a charity to fix the easy one.
"""
from __future__ import annotations

import dataclasses
import re
from decimal import Decimal

from .rules import ACKNOWLEDGMENT_THRESHOLD, QUID_PRO_QUO_THRESHOLD, CITATIONS, Donation

SEVERITY_ORDER = {"deduction-invalidating": 0, "charity-penalty": 1, "incomplete": 2, "style": 3}

# The negative statement, in the forms real letters use. Matching only Publication 1771's exact
# phrasing would flag correct letters that worded it differently, and an auditor that cries wolf
# gets ignored.
NO_GOODS = re.compile(
    r"no goods or services (were|was)?\s*(provided|received|given|exchanged)"
    r"|received no goods or services"
    r"|(you|the donor) did not receive (any )?(goods|goods or services)"
    r"|nothing (of value )?was (provided|given) in (exchange|return)", re.I)
INTANGIBLE = re.compile(r"intangible religious benefit", re.I)
# Deliberately not a proximity match. The required language runs "the amount ... that is
# deductible ... is limited to the excess of the amount contributed over the value of the goods
# provided. That amount is $60.00." The word and the figure are in different sentences and more
# than a hundred characters apart, so a windowed regex flags a correct letter. This looks for the
# word anywhere and the specific deductible figure anywhere, which is what a reader checks for.
DEDUCTIBLE_WORD = re.compile(r"deductible", re.I)
EIN = re.compile(r"\b\d{2}-\d{7}\b")
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
# A charity valuing donated property is the thing it must not do.
VALUED_PROPERTY = re.compile(
    r"(valued at|value of|worth|fair market value of|appraised at)\s*\$\s?[\d,]+", re.I)


@dataclasses.dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    detail: str
    citation: str

    def to_json(self) -> dict:
        return {"rule": self.rule, "severity": self.severity,
                "detail": self.detail, "citation": self.citation}


@dataclasses.dataclass(frozen=True)
class AuditResult:
    findings: tuple[Finding, ...]
    checks_run: int

    @property
    def passes(self) -> bool:
        return not any(f.severity in ("deduction-invalidating", "charity-penalty")
                       for f in self.findings)

    def to_json(self) -> dict:
        return {"passes": self.passes, "checks_run": self.checks_run,
                "findings": [f.to_json() for f in self.findings]}


def audit_letter(text: str, donation: Donation, charity_name: str = "",
                 ein: str = "") -> AuditResult:
    """Everything wrong with this letter, worst first."""
    findings: list[Finding] = []
    checks = 0

    def check(condition, rule, severity, detail, citation):
        nonlocal checks
        checks += 1
        if not condition:
            findings.append(Finding(rule, severity, detail, citation))

    low = text.lower()

    # The statement about goods and services. Required on every acknowledgment.
    if donation.is_quid_pro_quo:
        check(donation.goods_description.lower() in low or
              any(w in low for w in donation.goods_description.lower().split() if len(w) > 4),
              "goods described", "deduction-invalidating",
              "the donor received something and the letter does not say what",
              CITATIONS["no_goods_statement"])
        check(MONEY.search(text) is not None and str(donation.goods_value) in text.replace(",", ""),
              "good faith estimate", "charity-penalty",
              f"the letter does not state the ${donation.goods_value} estimated value of what "
              f"the donor received",
              CITATIONS["quid_pro_quo"])
    elif donation.intangible_religious:
        check(INTANGIBLE.search(text) is not None,
              "intangible religious benefit", "incomplete",
              "the gift was recorded as carrying only an intangible religious benefit and the "
              "letter does not say so",
              CITATIONS["intangible_religious"])
    else:
        check(NO_GOODS.search(text) is not None,
              "no goods or services statement", "deduction-invalidating",
              "the letter never states that no goods or services were provided. This is the most "
              "common defect in letters that fail examination, and its absence can cost the donor "
              "the whole deduction even though everything else is correct",
              CITATIONS["no_goods_statement"])

    # Quid pro quo over $75: the deductible amount must be stated.
    if donation.is_quid_pro_quo and donation.amount > QUID_PRO_QUO_THRESHOLD:
        stated = {Decimal(m.group(1).replace(",", "")) for m in MONEY.finditer(text)}
        check(DEDUCTIBLE_WORD.search(text) is not None and donation.deductible in stated,
              "deductible amount stated", "charity-penalty",
              f"a payment over ${QUID_PRO_QUO_THRESHOLD} where the donor received goods must "
              f"state that only the excess is deductible. The penalty for omitting it falls on "
              f"the charity, not the donor",
              CITATIONS["quid_pro_quo"])

    # A charity must not value donated property.
    if donation.kind in ("non-cash", "vehicle"):
        check(VALUED_PROPERTY.search(text) is None,
              "property not valued by the charity", "incomplete",
              "the letter attaches a value to donated property. Valuation is the donor's "
              "responsibility, and above $5,000 a qualified appraiser's, so a charity stating a "
              "figure has taken on a role the regulations assign elsewhere",
              CITATIONS["no_valuation"])
        check(any(w in low for w in donation.description.lower().split() if len(w) > 4),
              "property described", "deduction-invalidating",
              "a non-cash gift must be described and this letter does not describe it",
              CITATIONS["acknowledgment"])

    # Cash amount, for a cash gift over the acknowledgment threshold.
    if donation.kind == "cash" and donation.amount >= ACKNOWLEDGMENT_THRESHOLD:
        amounts = {Decimal(m.group(1).replace(",", "")) for m in MONEY.finditer(text)}
        check(donation.amount in amounts,
              "amount stated", "deduction-invalidating",
              f"the letter does not state the ${donation.amount} contributed",
              CITATIONS["acknowledgment"])

    # Vehicle donations carry their own form.
    if donation.kind == "vehicle":
        check("1098-c" in low, "Form 1098-C referenced", "incomplete",
              "a vehicle donation is substantiated on Form 1098-C and the letter does not "
              "mention it",
              CITATIONS["vehicle"])

    # Identification.
    check(str(donation.date.year) in text, "date present", "incomplete",
          "the letter does not carry the date of the contribution",
          CITATIONS["acknowledgment"])
    if charity_name:
        check(charity_name.lower() in low, "charity named", "deduction-invalidating",
              "the letter does not name the organisation that received the gift",
              CITATIONS["acknowledgment"])
    if ein:
        check(EIN.search(text) is not None, "EIN present", "style",
              "no EIN appears. It is not required by the statute and donors and auditors both "
              "look for it",
              CITATIONS["acknowledgment"])
    check(donation.donor_name.lower() in low, "donor named", "deduction-invalidating",
          "the letter does not name the donor",
          CITATIONS["acknowledgment"])

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.rule))
    return AuditResult(tuple(findings), checks)
