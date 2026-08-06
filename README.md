# donor-acknowledgment-letters

Generates IRS-compliant donor acknowledgment letters from a donation CSV, as text and as PDF,
plus year-end summary statements. It also **audits letters a charity already sent**, which is the
part worth having.

A substantiation letter is a legal instrument. If it is missing a required sentence, the donor's
deduction can be disallowed on audit. The person who loses is the donor, years later, with no way
to obtain a corrected letter, because the rule requires the acknowledgment to be contemporaneous.
Small charities send letters that would not survive that, in good faith, because the requirements
are counterintuitive.

## The two thresholds are different rules and they are constantly conflated

| | Threshold | Whose duty | What it requires |
|---|---|---|---|
| IRC 170(f)(8) | **$250 or more** | the donor's | above this the donor may not deduct without a contemporaneous written acknowledgment from the charity |
| IRC 6115 | **more than $75** | the charity's | on a quid pro quo contribution the charity must disclose that only the excess over the value received is deductible, and give a good faith estimate of that value |

They read differently in the statute and the tool treats them differently. $250 is inclusive,
$75 is strict. So:

- A **$100 gala ticket** where the dinner is worth $40 needs a disclosure and needs no acknowledgment.
- A **$300 cash gift** needs an acknowledgment and needs no disclosure.
- **Four $100 gifts totalling $400** need neither. The rule is per contribution, not per year, and
  this is the case charities most often get backwards in the other direction.
- A payment of **exactly $75** with goods received needs no disclosure. **Exactly $250** needs an
  acknowledgment.

## The sentence that matters most is a negative

A letter for a straightforward $500 cash gift must state that **no goods or services were provided
in exchange**. Its absence is the most common defect, because the drafter has nothing to report
and so reports nothing. This is the defect the auditor is built around.

## What a charity must not do

It must not state the value of donated property. Valuation is the donor's responsibility and above
$5,000 a qualified appraiser's. A charity that helpfully writes "thank you for your car, valued at
$4,000" has handed the donor a figure it did not appraise. Letters here describe the property and
refuse to price it, and say why, so the donor does not read the omission as an oversight.

## The auditor reads text, not the objects that produced it

This is the design decision the project rests on. `audit.py` takes a finished letter as a **string**
and applies the rules to it. Checking the generator's own data structures would confirm that two
halves of one program agree with each other, which they always will.

Because it reads text, three things follow:

1. It works on a letter written in Word by somebody who has never seen this tool. Point it at three
   years of back catalogue and it says which ones would not survive.
2. It can be run on text extracted back out of the finished **PDF**, which proves the document a
   donor actually receives carries the required language. `verify.sh` layer 5 does exactly that.
3. Its own defect tests use hand-typed letters rather than generated ones, so passing them is not
   circular.

Findings are ordered by consequence, not by position in the document:

| Severity | Meaning |
|---|---|
| `deduction-invalidating` | can cost the donor the whole deduction |
| `charity-penalty` | the penalty falls on the charity |
| `incomplete` | required content missing, consequences milder |
| `style` | untidy, not disqualifying |

A missing goods-and-services statement and a missing EIN are not the same problem, and presenting
them as a flat list invites a charity to fix the easy one.

## Run it

```
python3 -m donorack.cli rules     --csv corpus/donations.csv
python3 -m donorack.cli letters   --csv corpus/donations.csv --charity corpus/charity.json --out out
python3 -m donorack.cli summaries --csv corpus/donations.csv --charity corpus/charity.json --out out --year 2026
python3 -m donorack.cli audit out/*.pdf --csv corpus/donations.csv --charity corpus/charity.json
```

`letters` audits every letter before writing it and **exits non-zero if any has a defect**. A
generator that reports success for a letter missing a required sentence is worse than no tool,
because the charity now believes it is covered.

Column headers are matched however the donor database spelled them: `Donor Name`, `donor_name`,
`Gift Amount`, `Benefit Value`, `In-Kind`, `Car`. Dates in five formats. Rows that cannot be used
are reported **with their line numbers, all of them in one pass**, including rows that parse
cleanly but cannot produce a letter:

```
$ python3 -m donorack.cli letters --csv corpus/problem-rows.csv --charity corpus/charity.json --out out
  row 2: no date; an acknowledgment has to say when the gift was received
  row 3: 'three hundred' is not an amount
  row 4: a non-cash gift must be described, and no letter can be written without knowing what was received
  row 5: goods were valued but not described, and the disclosure has to say what the donor received
  row 6: the goods provided ($90.00) are worth more than the payment ($40.00), so this is a purchase rather than a contribution and no part of it is deductible
  row 7: the donor's name is missing, and an acknowledgment must identify them
```

## No dependencies

Generating letters and PDFs needs **nothing beyond the Python standard library**. A charity should
not have to install a rendering stack to send a thank-you note, so `pdfwrite.py` emits the PDF by
hand using the base fourteen fonts.

Line breaking uses the real Adobe AFM metrics for Helvetica, embedded as a table. `pdfminer.six` is
needed only to read PDFs back, which is verification rather than runtime.

## Verify

```
$ bash scripts/verify.sh
== 1. the package imports and the sources parse
  ok   every source file compiles
  ok   the package imports with nothing installed beyond the standard library
== 2. the unit suite
  ok   Ran 90 tests passed
== 3. the clean corpus generates letters and exits zero
  ok   14 letters and 14 PDFs from 14 donations
== 4. a corpus with bad rows exits non-zero and names every line
  ok   all six bad rows reported with their line numbers
== 5. every generated PDF still audits clean after extraction
  ok   14 letters checked, 0 with defects
== 6. and a defect introduced into one PDF is caught
  ok   the missing sentence was found and the command exited non-zero
== 7. the independent checker agrees, and imports nothing from the package
  ok     import graph of scripts/check_independent.py covers 1 file(s) and reaches none of donorack: scripts/check_independent.py
  ok   32 independent checks, 0 failed
== 8. year-end summaries
  ok   four gifts of $100 total $400 and the summary says it is not an acknowledgment
== 9. sabotage, under the three-gate rule
  ok   14/14 sabotages proven
       null control     a2cd6f497f5a26e3 matches, so the fingerprint tracks the code
== 10. nothing private is in any tracked file
  ok   the scanner finds a planted credential, so its silence below is informative
  ok   no home paths, no keys, no private repository names in 29 tracked files
  ok   the demo EIN uses prefix 00, which the IRS never issues, so it cannot be a real charity
== 11. the published page is the current output, not a stale copy
  ok   docs/index.html regenerates byte for byte from the corpus

VERIFY OK
```

### The three-gate sabotage rule

`scripts/sabotage.py` breaks the code fourteen ways. A sabotage counts only if it **applies**,
**changes the measured output**, and only then is **caught**. A sabotage that edits a branch
nothing reaches proves the checks did not notice a change that never happened, and it is reported
as `NO-OP`, which is a failure.

**The null control is the load-bearing part.** An unmodified copy of the tree, in a different
directory, must fingerprint identically to the baseline. The first version of this harness failed
that: the measurement included the CLI's `letters written to <out>` line, `<out>` was an absolute
path inside a per-sabotage temp directory, so every fingerprint differed for a reason unrelated to
the sabotage and gate 2 was satisfied automatically. Eleven sabotages scored as proven were proving
nothing. The control now runs first and aborts the whole run if it fails.

Three sabotages are **guard** sabotages, which invert gate 2. Disabling the auditor changes no
letter, because the auditor is dormant when the letters are correct, so for those the requirement
is stricter: the output must be **unchanged** and the unit suite must **fail**. A guard sabotage
that changes the letters is reported as `NOT-A-GUARD`. Two sabotages were reclassified by that
rule during development, and one, `pdf-escaping-off`, was a genuine no-op until a fixture was added
with an unclosed parenthesis in a description, because balanced parentheses are legal unescaped in
a PDF string and every description in the main corpus was balanced.

One sabotage, `auditor-cries-wolf`, is a **false-positive** attack. It restores an earlier
proximity regex that flagged a correct letter, because the required language puts the word
"deductible" and the dollar figure in different sentences more than 120 characters apart. An
auditor that cries wolf gets switched off, which is the same as having no auditor.

### The privacy scan has a positive control

Layer 10 plants a credential in a file the scanner will read and requires it to be found before
the real result is believed. It also fails if fewer than ten files are tracked, because before the
first commit `git ls-files` returns nothing and the layer passed without reading anything. Its
patterns are assembled from fragments rather than written out, since a scanner whose own pattern
list is a tracked file matches itself, and excluding the scanner would also stop it finding a real
leak in the scanner.

### The independent checker

`scripts/check_independent.py` reads the donation CSV and the finished letters with its own
parsing and applies the rules **retyped from Publication 1771**, importing nothing from `donorack`.
Independence is proved rather than asserted: `scripts/check_imports.py` walks the import graph with
Python's `ast` module and fails on any path reaching the package, on relative imports, and on a
dynamic import with a computed name, which cannot be followed and so cannot be cleared.

It also compares all 189 Helvetica and 189 Helvetica-Bold widths against the AFM copy inside
pdfminer, a third party that shares no code with this project.

## What this does not prove

- **That Publication 1771 says what both copies of the rules claim it says.** The package's rules
  and the independent checker's rules were transcribed by the same author, and two transcriptions
  by one author share a misreading. Every rule carries its citation so a reader can check it. A
  lawyer reading those citations is the check this cannot perform on itself.
- **That the AFM metrics are right.** The width check proves the shipped table matches Adobe's
  published metrics as pdfminer distributes them, not that Adobe is correct.
- **That a letter passing the audit will survive an examination.** It carries the language the
  publication requires. Facts, dates and amounts are the charity's to get right.

**This is not tax or legal advice.** A charity relying on it should have its template reviewed by
its own counsel, and every generated letter says so.

## The demo data is fictional

`corpus/charity.json` uses EIN prefix **00**, which the IRS never issues, so the example charity
cannot collide with a real organisation. Donor names and gifts are invented. `verify.sh` layer 10
checks the placeholder is still in place.

## Layout

```
donorack/rules.py      the thresholds and which requirements apply, with citations
donorack/letter.py     composition from named clauses, so a finished letter can be audited
donorack/audit.py      reads letter TEXT and reports defects worst first
donorack/csvin.py      the donation CSV, and every row that cannot be used
donorack/pdfwrite.py   a PDF writer in the standard library, with real font metrics
donorack/cli.py        letters, summaries, rules, audit
corpus/                fourteen donations covering every case, plus files of bad rows
scripts/verify.sh      ten layers; the exit code is the result
```

One of a public catalog of build ideas: https://github.com/JesseRWeigel/722-things-to-build

MIT.
