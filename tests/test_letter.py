"""Composition, and the things a letter must not say."""
import datetime
import unittest

from donorack.letter import Charity, Clause, clauses, compose, year_end_summary
from donorack.rules import Donation, money

MAY = datetime.date(2026, 5, 9)
CHARITY = Charity("Millrace Community Food Bank", "00-1234567",
                  "148 Mill Street, Millrace, IL 60000", "A. Chen", "Executive Director")


def names(donation):
    return [c.name for c in clauses(CHARITY, donation)]


class CharityValidation(unittest.TestCase):
    def test_ein_format(self):
        self.assertEqual(CHARITY.validate(), [])
        for bad in ("123456789x", "12-345678", "", "not an ein"):
            with self.subTest(bad):
                self.assertTrue(Charity("A", bad, "somewhere").validate())

    def test_ein_without_the_hyphen_is_accepted(self):
        # Nine digits is an EIN however it was typed; rejecting it would be the tool defending a
        # formatting preference rather than a rule.
        self.assertEqual(Charity("A", "123456789", "somewhere").validate(), [])

    def test_compose_refuses_rather_than_writing_a_defective_letter(self):
        with self.assertRaises(ValueError):
            compose(Charity("", "bad", ""), Donation("A", MAY, money("100"), "cash"))
        with self.assertRaises(ValueError):
            compose(CHARITY, Donation("", MAY, money("100"), "cash"))


class ClausesPresent(unittest.TestCase):
    def test_plain_cash_gets_the_negative_statement(self):
        self.assertIn("no-goods-statement", names(Donation("A", MAY, money("500"), "cash")))

    def test_quid_pro_quo_gets_goods_and_the_deductible_amount(self):
        gala = Donation("A", MAY, money("100"), "cash", goods_value=money("40"),
                        goods_description="a dinner")
        got = names(gala)
        self.assertIn("goods-provided", got)
        self.assertIn("deductible-amount", got)
        self.assertNotIn("no-goods-statement", got)

    def test_under_75_gets_goods_but_not_the_deductible_clause(self):
        # The disclosure duty starts above $75. Adding the clause anyway would be harmless-looking
        # and would tell the charity it owes something it does not.
        small = Donation("A", MAY, money("60"), "cash", goods_value=money("25"),
                         goods_description="a supper")
        got = names(small)
        self.assertIn("goods-provided", got)
        self.assertNotIn("deductible-amount", got)

    def test_non_cash_gets_the_no_valuation_clause(self):
        coats = Donation("A", MAY, money("0"), "non-cash", description="40 winter coats")
        self.assertIn("no-valuation", names(coats))

    def test_vehicle_gets_form_1098_c(self):
        car = Donation("A", MAY, money("0"), "vehicle", description="a 2011 Honda Civic",
                       vehicle_vin="1HGFA16511L000000")
        self.assertIn("vehicle", names(car))
        self.assertIn("1098-C", compose(CHARITY, car))

    def test_every_clause_is_named_so_a_finished_letter_can_be_audited(self):
        for c in clauses(CHARITY, Donation("A", MAY, money("500"), "cash")):
            self.assertIsInstance(c, Clause)
            self.assertTrue(c.name and c.text)


class ThingsALetterMustNotSay(unittest.TestCase):
    def test_a_non_cash_letter_states_no_dollar_figure(self):
        coats = Donation("Lena Fischer", MAY, money("0"), "non-cash",
                         description="40 winter coats in assorted adult sizes")
        text = compose(CHARITY, coats)
        self.assertNotIn("$", text)
        # And says why, so the donor does not assume it was an oversight.
        self.assertIn("donor's responsibility", text)

    def test_a_quid_pro_quo_letter_does_not_claim_the_whole_payment_is_deductible(self):
        gala = Donation("A", MAY, money("100"), "cash", goods_value=money("40"),
                        goods_description="a dinner")
        text = compose(CHARITY, gala)
        self.assertIn("$60.00", text)
        self.assertIn("limited to the excess", text)

    def test_the_disclaimer_is_present(self):
        self.assertIn("not tax or legal advice",
                      compose(CHARITY, Donation("A", MAY, money("500"), "cash")))


class YearEndSummary(unittest.TestCase):
    def setUp(self):
        self.rows = [Donation("Dana Okonkwo", datetime.date(2026, m, 14), money("100"), "cash")
                     for m in (2, 5, 8, 11)]
        self.rows.append(Donation("Dana Okonkwo", datetime.date(2025, 12, 1), money("999"),
                                  "cash"))

    def test_only_the_requested_year(self):
        text = year_end_summary(CHARITY, "Dana Okonkwo", self.rows, 2026)
        self.assertIn("$400.00", text)
        self.assertNotIn("999", text)

    def test_it_says_it_is_not_a_substitute_for_the_letters(self):
        # A summary that reads like an acknowledgment is worse than no summary, because the
        # charity stops sending the letters it still owes.
        text = year_end_summary(CHARITY, "Dana Okonkwo", self.rows, 2026)
        self.assertIn("does not replace those letters", text)

    def test_the_goods_statement_repeats_per_line(self):
        # The rule is per contribution, so one statement at the bottom does not cover the rows
        # above it.
        text = year_end_summary(CHARITY, "Dana Okonkwo", self.rows, 2026)
        self.assertEqual(text.count("no goods or services were provided in exchange"), 4)

    def test_deductible_total_excludes_the_value_of_goods(self):
        rows = [Donation("A", datetime.date(2026, 3, 1), money("100"), "cash",
                         goods_value=money("40"), goods_description="a dinner"),
                Donation("A", datetime.date(2026, 4, 1), money("200"), "cash")]
        text = year_end_summary(CHARITY, "A", rows, 2026)
        self.assertIn("Total contributed   $300.00", text)
        self.assertIn("Total deductible    $260.00", text)


if __name__ == "__main__":
    unittest.main()
