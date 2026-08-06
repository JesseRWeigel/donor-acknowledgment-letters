"""The PDF writer, and the round trip that proves the letter survives it.

The test that matters is the last class. Everything upstream can be correct and the donor still
receives a defective document if the PDF stage drops a sentence, so the auditor is run against
text extracted back out of the finished file rather than against the string that went in.
"""
import datetime
import unittest

from donorack.audit import audit_letter
from donorack.letter import Charity, compose
from donorack.pdfwrite import (HELVETICA, MARGIN, PAGE_HEIGHT, TEXT_WIDTH, Line, PdfEncodingError,
                               letter_pdf, paginate, render, width_of, wrap)
from donorack.rules import Donation, money

MAY = datetime.date(2026, 5, 9)
CHARITY = Charity("Millrace Community Food Bank", "00-1234567",
                  "148 Mill Street, Millrace, IL 60000", "A. Chen", "Executive Director")


class Widths(unittest.TestCase):
    def test_characters_have_different_widths(self):
        # The whole reason for the table. If these were equal the writer would be a monospace
        # approximation wearing a proportional font's name.
        self.assertGreater(width_of("W"), width_of("i"))
        self.assertGreater(width_of("m"), width_of("l"))

    def test_bold_is_wider_than_regular_for_lowercase(self):
        self.assertGreater(width_of("o", "Helvetica-Bold"), width_of("o", "Helvetica"))

    def test_width_scales_with_point_size(self):
        self.assertAlmostEqual(width_of("hello", size=22.0), 2 * width_of("hello", size=11.0))

    def test_a_character_with_no_metric_raises(self):
        # Guessing an average here would put every line a few points out, invisibly.
        with self.assertRaises(PdfEncodingError):
            width_of("中")


class Wrapping(unittest.TestCase):
    LONG = ("Thank you for your contribution. " * 12).strip()

    def test_no_line_exceeds_the_column(self):
        for line in wrap(self.LONG):
            self.assertLessEqual(width_of(line), TEXT_WIDTH, repr(line))

    def test_wrapping_loses_no_words(self):
        self.assertEqual(" ".join(wrap(self.LONG)).split(), self.LONG.split())

    def test_lines_are_reasonably_full(self):
        # A wrapper that broke after every word would satisfy the width assertion above, so this
        # is its negative control.
        lines = wrap(self.LONG)
        self.assertGreater(min(width_of(ln) for ln in lines[:-1]), TEXT_WIDTH * 0.75)

    def test_an_unbreakable_word_is_split_rather_than_overflowing(self):
        # A long account number or URL. Letting it run past the margin means the end of it is
        # not on the paper at all.
        word = "A" * 400
        lines = wrap(word)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(width_of(line), TEXT_WIDTH)
        self.assertEqual("".join(ln.rstrip("-") for ln in lines), word)

    def test_blank_lines_survive(self):
        self.assertEqual(wrap("a\n\nb"), ["a", "", "b"])


class Encoding(unittest.TestCase):
    def test_accented_names_are_written_not_mangled(self):
        self.assertIn(b"Jos\xe9", render([Line("José Martí Cruz")], compress=False))

    def test_a_name_outside_winansi_is_refused_rather_than_dropped(self):
        with self.assertRaises(PdfEncodingError) as cm:
            render([Line("田中太郎")])
        self.assertIn("U+", str(cm.exception))

    def test_parentheses_and_backslashes_are_escaped(self):
        raw = render([Line(r"(VIN 1HG) \ end")], compress=False)
        self.assertIn(rb"\(VIN 1HG\) \\ end", raw)


class Structure(unittest.TestCase):
    def test_a_pdf_starts_and_ends_the_way_a_pdf_does(self):
        pdf = letter_pdf("Dear Sam,\n\nThank you.")
        self.assertTrue(pdf.startswith(b"%PDF-1."))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_the_xref_offsets_point_at_real_objects(self):
        pdf = letter_pdf("Dear Sam,\n\nThank you.")
        start = int(pdf.split(b"startxref")[1].split(b"%%EOF")[0].strip())
        table = pdf[start:].split(b"\n")
        self.assertEqual(table[0], b"xref")
        count = int(table[1].split()[1])
        for i, row in enumerate(table[3:3 + count - 1], start=1):
            offset = int(row.split()[0])
            self.assertTrue(pdf[offset:].startswith(b"%d 0 obj" % i),
                            f"object {i} is not at offset {offset}")

    def test_long_content_paginates(self):
        lines = [Line(f"line {i}") for i in range(200)]
        pages = paginate(lines)
        self.assertGreater(len(pages), 1)
        for page in pages:
            for y, _ in page:
                self.assertGreaterEqual(y, MARGIN)
                self.assertLessEqual(y, PAGE_HEIGHT - MARGIN)
        self.assertEqual(sum(len(p) for p in pages), len(lines))


class RoundTrip(unittest.TestCase):
    """Extract the text back out of the PDF and audit that, not the string that went in."""

    def setUp(self):
        try:
            from pdfminer.high_level import extract_text  # noqa: F401
        except ImportError:
            self.skipTest("pdfminer.six is needed to read the PDF back")

    def extract(self, pdf: bytes) -> str:
        import io

        from pdfminer.high_level import extract_text
        return extract_text(io.BytesIO(pdf))

    def test_every_donation_kind_still_audits_clean_after_the_pdf_stage(self):
        cases = {
            "cash": Donation("Sam Ito", MAY, money("500"), "cash"),
            "gala": Donation("Priya Raman", MAY, money("100"), "cash", goods_value=money("40"),
                             goods_description="one dinner at the spring gala"),
            "coats": Donation("Lena Fischer", MAY, money("0"), "non-cash",
                              description="40 winter coats in assorted adult sizes"),
            "vehicle": Donation("Tomas Reyes", MAY, money("0"), "vehicle",
                                description="a 2011 Honda Civic sedan",
                                vehicle_vin="1HGFA16511L000000"),
        }
        for label, d in cases.items():
            with self.subTest(label):
                text = self.extract(letter_pdf(compose(CHARITY, d)))
                r = audit_letter(text, d, CHARITY.name, CHARITY.ein)
                self.assertTrue(r.passes, f"{label}: {[f.rule for f in r.findings]}")

    def test_a_defect_introduced_before_the_pdf_stage_is_still_visible_after_it(self):
        # The negative control for the test above. If extraction were returning something the
        # auditor cannot read, both would pass for the wrong reason.
        d = Donation("Sam Ito", MAY, money("500"), "cash")
        broken = compose(CHARITY, d).replace(
            "No goods or services were provided to you in exchange for this contribution.", "")
        r = audit_letter(self.extract(letter_pdf(broken)), d, CHARITY.name, CHARITY.ein)
        self.assertIn("no goods or services statement", {f.rule for f in r.findings})

    def test_the_dollar_amount_survives_extraction(self):
        d = Donation("Sam Ito", MAY, money("1500.50"), "cash")
        self.assertIn("$1,500.50", self.extract(letter_pdf(compose(CHARITY, d))))


if __name__ == "__main__":
    unittest.main()
