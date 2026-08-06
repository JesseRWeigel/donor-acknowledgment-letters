"""The thresholds, which is where this gets wrong in the wild.

Every threshold test is paired with its negative control. Asserting that $300 needs a letter
proves nothing on its own, because a function that returns True for everything passes it. The
pair that matters is the one straddling the boundary.
"""
import datetime
import unittest
from decimal import Decimal

from donorack.rules import (ACKNOWLEDGMENT_THRESHOLD, QUID_PRO_QUO_THRESHOLD, Donation,
                            DonationError, deadline, money, requirements, validate)

MAY = datetime.date(2026, 5, 9)


def cash(amount, goods=0, **kw):
    return Donation("Sam Ito", MAY, money(amount), "cash", goods_value=money(goods),
                    goods_description="a dinner" if goods else "", **kw)


def rule(donation, name):
    for r in requirements(donation):
        if r.rule == name:
            return r
    raise AssertionError(f"{name} is not among {[r.rule for r in requirements(donation)]}")


class Thresholds(unittest.TestCase):
    def test_acknowledgment_is_at_or_above_250(self):
        # 170(f)(8) says "$250 or more", so exactly $250 is inside the rule.
        self.assertFalse(rule(cash("249.99"), "written acknowledgment").required)
        self.assertTrue(rule(cash("250.00"), "written acknowledgment").required)
        self.assertTrue(rule(cash("250.01"), "written acknowledgment").required)

    def test_quid_pro_quo_is_strictly_above_75(self):
        # 6115 says "in excess of $75", so exactly $75 is outside the rule. The two thresholds
        # read differently in the statute and a tool that treats them the same is wrong on one.
        self.assertFalse(rule(cash("75.00", goods="20"), "quid pro quo disclosure").required)
        self.assertTrue(rule(cash("75.01", goods="20"), "quid pro quo disclosure").required)

    def test_the_two_thresholds_are_independent(self):
        # A $100 gala ticket needs a disclosure and does NOT need an acknowledgment.
        gala = cash("100", goods="40")
        self.assertTrue(rule(gala, "quid pro quo disclosure").required)
        self.assertFalse(rule(gala, "written acknowledgment").required)
        # A $300 cash gift is the mirror image.
        plain = cash("300")
        self.assertFalse(rule(plain, "quid pro quo disclosure").required)
        self.assertTrue(rule(plain, "written acknowledgment").required)

    def test_four_hundred_dollars_in_four_gifts_needs_no_letter(self):
        # The rule is per contribution. This is the case charities get wrong in the other
        # direction, sending letters they do not owe and believing the annual total is what counts.
        for _ in range(4):
            self.assertFalse(rule(cash("100"), "written acknowledgment").required)

    def test_intangible_religious_benefit_is_not_quid_pro_quo(self):
        pew = cash("300", goods="20", intangible_religious=True)
        self.assertFalse(pew.is_quid_pro_quo)
        self.assertFalse(rule(pew, "quid pro quo disclosure").required)
        self.assertIn("intangible", rule(pew, "quid pro quo disclosure").reason)
        # The control: the same gift without the flag does need the disclosure.
        self.assertTrue(rule(cash("300", goods="20"), "quid pro quo disclosure").required)


class Reasons(unittest.TestCase):
    def test_negative_requirements_carry_a_reason(self):
        for r in requirements(cash("100")):
            self.assertTrue(r.reason.strip(), f"{r.rule} has no reason")
            self.assertTrue(r.citation.strip(), f"{r.rule} has no citation")

    def test_reason_names_the_actual_threshold(self):
        r = rule(cash("100"), "written acknowledgment")
        self.assertIn(str(ACKNOWLEDGMENT_THRESHOLD), r.reason)
        r = rule(cash("60", goods="20"), "quid pro quo disclosure")
        self.assertIn(str(QUID_PRO_QUO_THRESHOLD), r.reason)


class Money(unittest.TestCase):
    def test_amounts_are_decimal_not_float(self):
        self.assertIsInstance(money("74.99"), Decimal)
        # The reason: three dimes is not 0.30 in binary floating point, and a threshold test on
        # the wrong side of a rounding artefact is a legal defect rather than a cosmetic one.
        self.assertEqual(money("0.10") * 3, Decimal("0.30"))

    def test_refuses_what_is_not_an_amount(self):
        for bad in ("three hundred", None, "", "abc"):
            with self.assertRaises(DonationError):
                money(bad)

    def test_refuses_negative(self):
        with self.assertRaises(DonationError):
            money("-5")

    def test_accepts_the_formats_a_spreadsheet_exports(self):
        self.assertEqual(money("$1,250.00"), Decimal("1250.00"))
        self.assertEqual(money(" 1250 "), Decimal("1250.00"))

    def test_deductible_never_negative(self):
        # Goods worth more than the payment is a purchase, and the deductible part is zero
        # rather than a negative number that would flow into a summary total.
        d = Donation("A", MAY, money("40"), "non-cash", description="a print",
                     goods_value=money("90"), goods_description="a framed print")
        self.assertEqual(d.deductible, Decimal("0"))


class Validate(unittest.TestCase):
    def test_each_problem_is_caught_and_a_good_donation_is_not(self):
        self.assertEqual(validate(cash("300")), [])
        cases = {
            "name": Donation("", MAY, money("300"), "cash"),
            "kind": Donation("A", MAY, money("300"), "gift card"),
            "description": Donation("A", MAY, money("0"), "non-cash"),
            "goods described": Donation("A", MAY, money("300"), "cash",
                                        goods_value=money("50")),
            "purchase": Donation("A", MAY, money("40"), "cash", goods_value=money("90"),
                                 goods_description="a print"),
            "vin": Donation("A", MAY, money("0"), "vehicle", description="a car"),
        }
        for label, donation in cases.items():
            with self.subTest(label):
                self.assertTrue(validate(donation), f"{label} was accepted")


class Deadline(unittest.TestCase):
    def test_default_is_the_following_april(self):
        self.assertEqual(deadline(cash("300")), datetime.date(2027, 4, 15))

    def test_a_supplied_filing_date_wins_because_it_is_earlier(self):
        early = datetime.date(2027, 2, 1)
        self.assertEqual(deadline(cash("300"), early), early)


if __name__ == "__main__":
    unittest.main()
