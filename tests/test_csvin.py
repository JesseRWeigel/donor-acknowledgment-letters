"""Reading the CSV, and reporting what could not be read.

Every assertion about a rejected row also checks the LINE NUMBER, because "some rows were bad" is
not actionable and the bookkeeper has the file open in front of them.
"""
import datetime
import unittest
from decimal import Decimal

from donorack.csvin import parse_date, read_rows
from donorack.rules import DonationError

HEADER = ("donor_name,date,amount,kind,description,goods_value,goods_description,"
          "intangible_religious,vehicle_vin,vehicle_gross_proceeds\n")


def one(row):
    return read_rows(HEADER + row + "\n")


class Reading(unittest.TestCase):
    def test_a_plain_row(self):
        got, errors = one("Sam Ito,2026-05-09,500.00,cash,,,,no,,")
        self.assertEqual(errors, [])
        self.assertEqual(len(got), 1)
        d = got[0]
        self.assertEqual(d.donor_name, "Sam Ito")
        self.assertEqual(d.date, datetime.date(2026, 5, 9))
        self.assertEqual(d.amount, Decimal("500.00"))
        self.assertEqual(d.kind, "cash")

    def test_headers_are_matched_however_the_export_spelled_them(self):
        got, errors = read_rows(
            "Donor Name,Gift Date,Gift Amount,Type\n"
            'Hana Suzuki,"March 8, 2026",600.00,Cash\n')
        self.assertEqual(errors, [])
        self.assertEqual(got[0].donor_name, "Hana Suzuki")
        self.assertEqual(got[0].amount, Decimal("600.00"))

    def test_kind_synonyms_map_onto_the_three_the_rules_know(self):
        for spelling, expected in (("In-Kind", "non-cash"), ("property", "non-cash"),
                                   ("Car", "vehicle"), ("automobile", "vehicle"),
                                   ("CASH", "cash")):
            with self.subTest(spelling):
                extra = ",1HGFA16511L000000," if expected == "vehicle" else ",,"
                got, errors = one(f"A,2026-01-01,0,{spelling},a thing,,,no{extra}")
                self.assertEqual(errors, [], f"{spelling}: {[e.problem for e in errors]}")
                self.assertEqual(got[0].kind, expected)

    def test_a_missing_required_column_is_refused_with_the_headers_it_did_find(self):
        with self.assertRaises(DonationError) as cm:
            read_rows("amount,notes\n100,hello\n")
        self.assertIn("donor_name", str(cm.exception))
        self.assertIn("amount", str(cm.exception))

    def test_a_byte_order_mark_does_not_become_part_of_the_first_header(self):
        # Excel writes one, and it turns `donor_name` into `﻿donor_name`, which would fail
        # the required-column check with a message that makes no sense to read.
        got, errors = read_rows("﻿donor_name,date,amount,kind\nA,2026-01-01,10,cash\n")
        self.assertEqual(errors, [])
        self.assertEqual(got[0].donor_name, "A")


class Dates(unittest.TestCase):
    def test_the_formats_a_donor_database_exports(self):
        expected = datetime.date(2026, 3, 8)
        for text in ("2026-03-08", "03/08/2026", "3/8/26", "March 8, 2026", "Mar 8, 2026"):
            with self.subTest(text):
                self.assertEqual(parse_date(text), expected)

    def test_an_unrecognised_date_is_refused_and_says_what_it_accepts(self):
        with self.assertRaises(DonationError) as cm:
            parse_date("the eighth of March")
        self.assertIn("%Y-%m-%d", str(cm.exception))

    def test_a_missing_date_is_refused(self):
        with self.assertRaises(DonationError):
            parse_date("")


class Rejections(unittest.TestCase):
    """Rows that parse and rows that do not, both reported with a line number."""

    def test_each_kind_of_bad_row_is_reported_once_with_its_line(self):
        text = (
            "donor_name,date,amount,kind,description,goods_value,goods_description\n"
            "Ann Meyer,,300.00,cash,,,\n"                       # 2: no date
            "Bo Tran,2026-03-02,three hundred,cash,,,\n"        # 3: amount is not a number
            "Cal Ortiz,2026-03-03,0.00,non-cash,,,\n"           # 4: no description
            "Di Novak,2026-03-04,200.00,cash,,50.00,\n"         # 5: goods valued, not described
            "Eli Park,2026-03-05,40.00,cash,,90.00,a print\n"   # 6: a purchase, not a gift
            ",2026-03-06,500.00,cash,,,\n"                      # 7: no donor
            "Gia Russo,03/07/2026,150.00,cash,,,\n")            # 8: fine
        got, errors = read_rows(text)
        self.assertEqual([e.line for e in errors], [2, 3, 4, 5, 6, 7])
        self.assertEqual([d.donor_name for d in got], ["Gia Russo"])

    def test_a_row_that_parses_but_cannot_produce_a_letter_is_an_error_not_a_donation(self):
        # It reads perfectly well as CSV and is still useless, and finding out at generation
        # time means another round trip for the bookkeeper.
        got, errors = one("Cal Ortiz,2026-03-03,0.00,non-cash,,,,no,,")
        self.assertEqual(got, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("must be described", errors[0].problem)

    def test_the_offending_row_is_returned_so_it_can_be_shown(self):
        _, errors = one("Bo Tran,2026-03-02,three hundred,cash,,,,no,,")
        self.assertEqual(errors[0].row["donor_name"], "Bo Tran")

    def test_one_bad_row_does_not_stop_the_rest(self):
        got, errors = read_rows(HEADER
                                + "Bo Tran,2026-03-02,three hundred,cash,,,,no,,\n"
                                + "Sam Ito,2026-05-09,500.00,cash,,,,no,,\n")
        self.assertEqual(len(got), 1)
        self.assertEqual(len(errors), 1)


class Flags(unittest.TestCase):
    def test_yes_and_no_in_the_spellings_people_use(self):
        for text, expected in (("yes", True), ("Y", True), ("TRUE", True), ("1", True),
                               ("no", False), ("", False), ("0", False)):
            with self.subTest(text):
                got, errors = one(f"A,2026-01-01,300,cash,,20.00,a supper,{text},,")
                self.assertEqual(errors, [])
                self.assertEqual(got[0].intangible_religious, expected)

    def test_anything_else_is_refused_rather_than_read_as_false(self):
        # Reading "maybe" as no would silently turn a church offering into a quid pro quo
        # contribution and put a disclosure in the letter that does not belong there.
        _, errors = one("A,2026-01-01,300,cash,,20.00,a supper,maybe,,")
        self.assertEqual(len(errors), 1)
        self.assertIn("yes or no", errors[0].problem)


if __name__ == "__main__":
    unittest.main()
