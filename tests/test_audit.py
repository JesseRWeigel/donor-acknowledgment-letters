"""The auditor, tested on letters it did not generate.

The point of every test here is that the auditor reads TEXT. Feeding it only letters that
`compose` produced would test that two halves of the same program agree with each other, which
they always will. So the letters below are typed out the way a charity's Word template would
have them, defects and all.
"""
import datetime
import unittest

from donorack.audit import SEVERITY_ORDER, audit_letter
from donorack.letter import Charity, compose
from donorack.rules import Donation, money

MAY = datetime.date(2026, 5, 9)
CHARITY = Charity("Millrace Community Food Bank", "00-1234567",
                  "148 Mill Street, Millrace, IL 60000", "A. Chen", "Executive Director")

PLAIN = Donation("Sam Ito", MAY, money("500"), "cash")
GALA = Donation("Priya Raman", MAY, money("100"), "cash", goods_value=money("40"),
                goods_description="one dinner at the spring gala")
COATS = Donation("Lena Fischer", MAY, money("0"), "non-cash",
                 description="40 winter coats in assorted adult sizes")

# A letter of the kind that actually gets sent, and the reason this project exists. Everything
# about it is warm and correct except that it never says no goods or services were provided.
HANDWRITTEN_MISSING_NEGATIVE = """Dear Sam Ito,

On behalf of everyone at Millrace Community Food Bank, thank you so much for your wonderful
gift of $500.00, which we received on May 9, 2026. Your generosity means that families in our
community will eat this winter.

Our EIN is 00-1234567.

With gratitude,
A. Chen
"""

HANDWRITTEN_CORRECT = HANDWRITTEN_MISSING_NEGATIVE.replace(
    "Our EIN", "No goods or services were provided in exchange for this contribution.\n\nOur EIN")

# The other common defect: a charity being helpful about a value it has no business stating.
HANDWRITTEN_VALUED_PROPERTY = """Dear Lena Fischer,

Thank you for your donation of 40 winter coats in assorted adult sizes, received on May 9, 2026,
valued at $1,200.00. No goods or services were provided in exchange for this contribution.

Millrace Community Food Bank, EIN 00-1234567.
"""


def rules_found(result):
    return {f.rule for f in result.findings}


class ReadsTextNotObjects(unittest.TestCase):
    def test_catches_the_missing_negative_statement(self):
        r = audit_letter(HANDWRITTEN_MISSING_NEGATIVE, PLAIN, CHARITY.name, CHARITY.ein)
        self.assertIn("no goods or services statement", rules_found(r))
        self.assertFalse(r.passes)

    def test_and_passes_the_same_letter_once_the_sentence_is_added(self):
        # The negative control for the test above. Without it, an auditor that failed every
        # letter would score identically.
        r = audit_letter(HANDWRITTEN_CORRECT, PLAIN, CHARITY.name, CHARITY.ein)
        self.assertEqual(rules_found(r), set())
        self.assertTrue(r.passes)

    def test_catches_a_charity_valuing_donated_property(self):
        r = audit_letter(HANDWRITTEN_VALUED_PROPERTY, COATS, CHARITY.name, CHARITY.ein)
        self.assertIn("property not valued by the charity", rules_found(r))

    def test_and_passes_when_the_value_is_removed(self):
        clean = HANDWRITTEN_VALUED_PROPERTY.replace(",\nvalued at $1,200.00", "")
        r = audit_letter(clean, COATS, CHARITY.name, CHARITY.ein)
        self.assertNotIn("property not valued by the charity", rules_found(r))

    def test_accepts_wording_that_is_not_publication_1771_verbatim(self):
        # A tool that only recognises the sample language flags correct letters, and an auditor
        # that cries wolf gets switched off.
        for phrasing in ("You did not receive any goods or services in return.",
                         "Nothing of value was provided in exchange.",
                         "The donor received no goods or services."):
            with self.subTest(phrasing):
                text = HANDWRITTEN_MISSING_NEGATIVE.replace("Our EIN", phrasing + "\n\nOur EIN")
                r = audit_letter(text, PLAIN, CHARITY.name, CHARITY.ein)
                self.assertNotIn("no goods or services statement", rules_found(r))


class GeneratedLettersPass(unittest.TestCase):
    def test_every_case_the_generator_handles_audits_clean(self):
        vehicle = Donation("Tomas Reyes", MAY, money("0"), "vehicle",
                           description="a 2011 Honda Civic sedan",
                           vehicle_vin="1HGFA16511L000000")
        religious = Donation("Ruth Adeyemi", MAY, money("300"), "cash", goods_value=money("20"),
                             goods_description="a place at the parish supper",
                             intangible_religious=True)
        for label, d in {"cash": PLAIN, "gala": GALA, "coats": COATS,
                         "vehicle": vehicle, "religious": religious}.items():
            with self.subTest(label):
                r = audit_letter(compose(CHARITY, d), d, CHARITY.name, CHARITY.ein)
                self.assertTrue(r.passes, f"{label}: {rules_found(r)}")
                self.assertGreaterEqual(r.checks_run, 4)


class DefectsAreDetected(unittest.TestCase):
    """Each one removes a required part from a correct letter and confirms the auditor notices.

    A checker that never fails is the failure mode this whole project exists to prevent, so each
    case asserts the clean letter passes first.
    """

    def _mutate(self, donation, find, replace):
        good = compose(CHARITY, donation)
        self.assertTrue(audit_letter(good, donation, CHARITY.name, CHARITY.ein).passes)
        self.assertIn(find, good, "the mutation did not apply, so it proves nothing")
        return audit_letter(good.replace(find, replace), donation, CHARITY.name, CHARITY.ein)

    def test_amount_removed(self):
        r = self._mutate(PLAIN, "$500.00", "a generous sum")
        self.assertIn("amount stated", rules_found(r))

    def test_negative_statement_removed(self):
        r = self._mutate(PLAIN, "No goods or services were provided to you in exchange for this "
                                "contribution.", "")
        self.assertIn("no goods or services statement", rules_found(r))

    def test_good_faith_estimate_removed(self):
        r = self._mutate(GALA, "$40.00", "a modest amount")
        self.assertIn("good faith estimate", rules_found(r))

    def test_deductible_amount_removed(self):
        r = self._mutate(GALA, "That amount is $60.00.", "")
        self.assertIn("deductible amount stated", rules_found(r))

    def test_donor_name_removed(self):
        r = self._mutate(PLAIN, "Sam Ito", "Valued Supporter")
        self.assertIn("donor named", rules_found(r))

    def test_ein_removed(self):
        r = self._mutate(PLAIN, "00-1234567", "on file")
        self.assertIn("EIN present", rules_found(r))

    def test_property_description_removed(self):
        r = self._mutate(COATS, "40 winter coats in assorted adult sizes", "your kind gift")
        self.assertIn("property described", rules_found(r))


class Severity(unittest.TestCase):
    def test_missing_ein_alone_does_not_fail_the_letter(self):
        # It is untidy, not disqualifying, and conflating the two makes the report useless for
        # deciding what to fix first.
        text = HANDWRITTEN_CORRECT.replace("00-1234567", "on file")
        r = audit_letter(text, PLAIN, CHARITY.name, CHARITY.ein)
        self.assertIn("EIN present", rules_found(r))
        self.assertTrue(r.passes)

    def test_findings_are_ordered_worst_first(self):
        text = HANDWRITTEN_MISSING_NEGATIVE.replace("00-1234567", "on file")
        text = text.replace("$500.00", "a generous sum")
        r = audit_letter(text, PLAIN, CHARITY.name, CHARITY.ein)
        self.assertGreater(len(r.findings), 1)
        ranks = [SEVERITY_ORDER[f.severity] for f in r.findings]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(r.findings[0].severity, "deduction-invalidating")

    def test_checks_run_is_reported_so_a_pass_has_a_denominator(self):
        # "No findings" from an auditor that ran zero checks is the same output as a clean
        # letter, and the count is what tells them apart.
        r = audit_letter(compose(CHARITY, PLAIN), PLAIN, CHARITY.name, CHARITY.ein)
        self.assertGreater(r.checks_run, 0)
        self.assertEqual(r.to_json()["checks_run"], r.checks_run)


if __name__ == "__main__":
    unittest.main()
