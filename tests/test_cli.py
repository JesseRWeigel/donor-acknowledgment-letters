"""The command line, run as a subprocess, because the exit code is the deliverable.

A charity puts this in a cron job or a Makefile. If the command prints "3 letters have defects"
and exits 0, the pipeline reports success and nobody looks.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"


def run(*args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "donorack.cli", *args],
                          cwd=cwd, capture_output=True, text=True)


class Letters(unittest.TestCase):
    def test_the_clean_corpus_generates_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as out:
            r = run("letters", "--csv", str(CORPUS / "donations.csv"),
                    "--charity", str(CORPUS / "charity.json"), "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            written = sorted(pathlib.Path(out).glob("*.txt"))
            self.assertEqual(len(written), 14)
            self.assertEqual(len(sorted(pathlib.Path(out).glob("*.pdf"))), 14)

    def test_the_problem_corpus_exits_nonzero_and_names_every_line(self):
        with tempfile.TemporaryDirectory() as out:
            r = run("letters", "--csv", str(CORPUS / "problem-rows.csv"),
                    "--charity", str(CORPUS / "charity.json"), "--out", out)
            self.assertEqual(r.returncode, 1)
            for line in (2, 3, 4, 5, 6, 7):
                self.assertIn(f"row {line}:", r.stderr)

    def test_charity_is_required(self):
        with tempfile.TemporaryDirectory() as out:
            r = run("letters", "--csv", str(CORPUS / "donations.csv"), "--out", out)
            self.assertEqual(r.returncode, 2)
            self.assertIn("--charity", r.stderr)

    def test_a_missing_file_is_an_error_not_a_traceback(self):
        r = run("letters", "--csv", "nope.csv", "--charity", str(CORPUS / "charity.json"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


class AuditCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = pathlib.Path(self.tmp.name)
        r = run("letters", "--csv", str(CORPUS / "donations.csv"),
                "--charity", str(CORPUS / "charity.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_generated_pdf_audits_clean(self):
        # The end to end claim: the auditor reads the PDF a donor would receive.
        pdfs = [str(p) for p in sorted(self.out.glob("*.pdf"))]
        r = run("audit", *pdfs, "--csv", str(CORPUS / "donations.csv"),
                "--charity", str(CORPUS / "charity.json"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("14 letters checked, 0 with defects", r.stdout)

    def test_a_defective_letter_is_caught_and_exits_nonzero(self):
        # The negative control for the test above. Remove the one sentence that matters.
        target = self.out / "2026-05-09-sam-ito.txt"
        text = target.read_text(encoding="utf-8")
        marker = "No goods or services were provided to you in exchange for this contribution."
        self.assertIn(marker, text, "the mutation did not apply, so it proves nothing")
        target.write_text(text.replace(marker, ""), encoding="utf-8")

        r = run("audit", str(target), "--csv", str(CORPUS / "donations.csv"),
                "--charity", str(CORPUS / "charity.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("no goods or services statement", r.stdout)
        self.assertIn("deduction-invalidating", r.stdout)

    def test_a_letter_matching_two_donations_is_reported_ambiguous_rather_than_guessed(self):
        # Priya Raman gave twice, and the two gifts have different requirements. Checking the
        # September letter against the March gift reports defects that are not in the letter.
        letter = self.out / "2026-09-12-priya-raman.txt"
        stripped = letter.read_text(encoding="utf-8").replace("September 12, 2026", "some time")
        ambiguous = self.out / "ambiguous.txt"
        ambiguous.write_text(stripped, encoding="utf-8")

        r = run("audit", str(ambiguous), "--csv", str(CORPUS / "donations.csv"),
                "--charity", str(CORPUS / "charity.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("ambiguous", r.stderr)

    def test_a_letter_naming_nobody_in_the_csv_is_refused_not_passed(self):
        stranger = self.out / "stranger.txt"
        stranger.write_text("Dear Nobody At All,\n\nThank you.\n", encoding="utf-8")
        r = run("audit", str(stranger), "--csv", str(CORPUS / "donations.csv"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to check it against", r.stderr)


class Summaries(unittest.TestCase):
    def test_one_per_donor_for_the_requested_year(self):
        with tempfile.TemporaryDirectory() as out:
            r = run("summaries", "--csv", str(CORPUS / "donations.csv"),
                    "--charity", str(CORPUS / "charity.json"), "--out", out, "--year", "2026")
            self.assertEqual(r.returncode, 0, r.stderr)
            files = sorted(pathlib.Path(out).glob("*.txt"))
            self.assertEqual(len(files), 10)  # 14 gifts, 10 distinct donors
            dana = [f for f in files if "dana" in f.name][0]
            self.assertIn("$400.00", dana.read_text(encoding="utf-8"))

    def test_a_year_with_no_gifts_produces_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as out:
            r = run("summaries", "--csv", str(CORPUS / "donations.csv"),
                    "--charity", str(CORPUS / "charity.json"), "--out", out, "--year", "1999")
            self.assertEqual(r.returncode, 0)
            self.assertIn("0 summaries", r.stdout)


class Rules(unittest.TestCase):
    def test_it_explains_the_negative_cases_too(self):
        r = run("rules", "--csv", str(CORPUS / "donations.csv"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not req ", r.stdout)
        self.assertIn("REQUIRED", r.stdout)
        self.assertIn("IRC 6115", r.stdout)


if __name__ == "__main__":
    unittest.main()
