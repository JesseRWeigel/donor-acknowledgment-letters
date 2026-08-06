"""Build docs/index.html from the corpus, so the page cannot drift from the code.

Every letter, requirement and finding on the published page is produced by running the tool here,
at build time. Nothing on it is typed by hand. A hand-written example page is a claim about the
software; a generated one is the software's output.
"""
from __future__ import annotations

import datetime
import html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from donorack.audit import audit_letter                                        # noqa: E402
from donorack.csvin import read_file                                           # noqa: E402
from donorack.letter import Charity, compose, year_end_summary                 # noqa: E402
from donorack.rules import (ACKNOWLEDGMENT_THRESHOLD, QUID_PRO_QUO_THRESHOLD,  # noqa: E402
                            requirements)

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = html.escape

CSS = """
:root{
  --paper:#f7f7f4; --card:#fffffe; --ink:#14161a; --ink-2:#4a5058; --ink-3:#7b828c;
  --rule:#d8d9d4; --rule-2:#eceded; --accent:#1b3a5c; --accent-soft:#e6edf4;
  --flag:#8f2f22; --flag-soft:#f6e8e5; --ok:#1f5d3f; --ok-soft:#e4efe8;
  --mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
  --text:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#101215; --card:#171a1e; --ink:#e9eaec; --ink-2:#a8aeb6; --ink-3:#767d86;
    --rule:#2b2f35; --rule-2:#22262b; --accent:#8fb6dd; --accent-soft:#1a242f;
    --flag:#e08a7c; --flag-soft:#2a1d1a; --ok:#7fc4a0; --ok-soft:#16241d;
  }
}
:root[data-theme="dark"]{
  --paper:#101215; --card:#171a1e; --ink:#e9eaec; --ink-2:#a8aeb6; --ink-3:#767d86;
  --rule:#2b2f35; --rule-2:#22262b; --accent:#8fb6dd; --accent-soft:#1a242f;
  --flag:#e08a7c; --flag-soft:#2a1d1a; --ok:#7fc4a0; --ok-soft:#16241d;
}
:root[data-theme="light"]{
  --paper:#f7f7f4; --card:#fffffe; --ink:#14161a; --ink-2:#4a5058; --ink-3:#7b828c;
  --rule:#d8d9d4; --rule-2:#eceded; --accent:#1b3a5c; --accent-soft:#e6edf4;
  --flag:#8f2f22; --flag-soft:#f6e8e5; --ok:#1f5d3f; --ok-soft:#e4efe8;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--text);
  font-size:17px;line-height:1.6;-webkit-text-size-adjust:100%}
.wrap{max-width:56rem;margin:0 auto;padding:0 1.25rem 6rem}
header{border-bottom:2px solid var(--ink);padding:3.5rem 0 1.25rem;margin-bottom:2.5rem}
.eyebrow{font-family:var(--ui);font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 .75rem}
h1{font-family:var(--ui);font-size:clamp(1.9rem,5vw,2.9rem);line-height:1.08;margin:0 0 .6rem;
  font-weight:640;letter-spacing:-.02em;text-wrap:balance}
.lede{font-size:1.16rem;color:var(--ink-2);margin:0;max-width:44rem;text-wrap:pretty}
h2{font-family:var(--ui);font-size:1.32rem;font-weight:640;letter-spacing:-.01em;
  margin:3.25rem 0 .4rem;text-wrap:balance}
h3{font-family:var(--ui);font-size:.74rem;letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink-3);font-weight:620;margin:2rem 0 .6rem}
p{margin:0 0 1rem;max-width:44rem;text-wrap:pretty}
a{color:var(--accent)}
.sub{color:var(--ink-2);font-size:.97rem}
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));
  margin:1.25rem 0 0}
.card{background:var(--card);border:1px solid var(--rule);padding:1.1rem 1.15rem}
.card .k{font-family:var(--mono);font-size:1.7rem;font-variant-numeric:tabular-nums;
  letter-spacing:-.03em;display:block;margin-bottom:.15rem}
.card .n{font-family:var(--ui);font-size:.7rem;letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink-3);display:block;margin-bottom:.5rem}
.card .d{font-size:.92rem;color:var(--ink-2);margin:0}
.scroll{overflow-x:auto;margin:1.25rem 0;border:1px solid var(--rule);background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:.9rem}
caption{text-align:left;font-family:var(--ui);font-size:.72rem;letter-spacing:.11em;
  text-transform:uppercase;color:var(--ink-3);padding:.8rem 1rem .1rem}
th{font-family:var(--ui);font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-3);text-align:left;font-weight:620;padding:.7rem 1rem;
  border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:.62rem 1rem;border-bottom:1px solid var(--rule-2);vertical-align:top}
td.tight{white-space:nowrap}
tr:last-child td{border-bottom:0}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{font-family:var(--ui);font-size:.66rem;letter-spacing:.07em;text-transform:uppercase;
  padding:.16rem .45rem;border:1px solid currentColor;white-space:nowrap;font-weight:600}
.req{color:var(--accent);background:var(--accent-soft)}
.no{color:var(--ink-3)}
.pass{color:var(--ok);background:var(--ok-soft)}
.cite{font-family:var(--mono);font-size:.76rem;color:var(--ink-3);white-space:nowrap}
.letter{background:var(--card);border:1px solid var(--rule);padding:1.5rem 1.6rem;
  white-space:pre-wrap;font-size:.94rem;line-height:1.66;overflow-x:auto}
.letter .mark{background:var(--accent-soft);border-bottom:1px solid var(--accent);
  padding:.05em 0}
pre{font-family:var(--mono);font-size:.82rem;line-height:1.55;background:var(--card);
  border:1px solid var(--rule);padding:1rem 1.1rem;overflow-x:auto;margin:1rem 0}
.finding{border-left:3px solid var(--flag);background:var(--flag-soft);padding:.7rem .95rem;
  margin:.6rem 0;font-size:.93rem}
.finding b{font-family:var(--ui);font-size:.78rem;letter-spacing:.05em;text-transform:uppercase}
.two{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fit,minmax(19rem,1fr))}
footer{margin-top:4.5rem;padding-top:1.25rem;border-top:1px solid var(--rule);
  font-size:.88rem;color:var(--ink-3)}
.warn{border:1px solid var(--rule);border-left:3px solid var(--ink-3);padding:.9rem 1.1rem;
  font-size:.93rem;color:var(--ink-2);background:var(--card);margin:1.25rem 0}
"""


def money(v):
    return f"${v:,.2f}"


def table(caption, headers, rows, aligns=None):
    aligns = aligns or [""] * len(headers)
    out = [f'<div class="scroll"><table><caption>{E(caption)}</caption><thead><tr>']
    out += [f"<th>{E(h)}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell, align in zip(row, aligns):
            out.append(f'<td class="{align}">{cell}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def main():
    charity = Charity(**{k: v for k, v in
                         __import__("json").loads(
                             (ROOT / "corpus/charity.json").read_text(encoding="utf-8")).items()
                         if not k.startswith("_")})
    donations, errors = read_file(ROOT / "corpus/donations.csv")
    _, bad_rows = read_file(ROOT / "corpus/problem-rows.csv")

    # 1. Every donation, and what the rules say about it. Generated, not typed.
    rows = []
    for d in donations:
        reqs = {r.rule: r for r in requirements(d)}
        ack = reqs["written acknowledgment"]
        qpq = reqs["quid pro quo disclosure"]

        def tag(r):
            cls = "tag req" if r.required else "tag no"
            return f'<span class="{cls}">{"required" if r.required else "not required"}</span>'

        rows.append([
            E(d.donor_name),
            f'<span class="num">{d.date}</span>',
            f'<span class="num">{money(d.amount) if d.amount else "&mdash;"}</span>'
            if d.amount else '<span class="num">&mdash;</span>',
            E(d.kind),
            f'<span class="num">{money(d.goods_value)}</span>' if d.goods_value
            else '<span class="num">&mdash;</span>',
            tag(ack), tag(qpq),
        ])
    donation_table = table(
        f"every donation in the corpus. 170(f)(8) applies at "
        f"{money(ACKNOWLEDGMENT_THRESHOLD)} or more; 6115 applies above "
        f"{money(QUID_PRO_QUO_THRESHOLD)} when goods were received",
        ["Donor", "Date", "Paid", "Kind", "Value received",
         "170(f)(8) letter", "6115 disclosure"],
        rows, ["tight", "num", "num", "tight", "num", "", ""])

    # 2. The gala letter, with the two clauses that exist only because of section 6115.
    gala = next(d for d in donations if d.is_quid_pro_quo
                and d.amount > QUID_PRO_QUO_THRESHOLD)
    gala_text = compose(charity, gala)
    marked = E(gala_text)
    for phrase in (f"for which we make a good faith estimate of value of {money(gala.goods_value)}",
                   f"That amount is {money(gala.deductible)}."):
        marked = marked.replace(E(phrase), f'<span class="mark">{E(phrase)}</span>')

    # 3. A real audit of a defective letter, run here rather than described.
    plain = next(d for d in donations if d.kind == "cash" and not d.is_quid_pro_quo
                 and d.amount >= ACKNOWLEDGMENT_THRESHOLD)
    good = compose(charity, plain)
    marker = "No goods or services were provided to you in exchange for this contribution.\n\n"
    assert marker in good, "the demonstration mutation no longer applies"
    broken = good.replace(marker, "").replace(money(plain.amount), "a generous sum")
    result = audit_letter(broken, plain, charity.name, charity.ein)
    assert not result.passes, "the demonstration letter is supposed to fail"
    findings = "".join(
        f'<div class="finding"><b>{E(f.severity)}</b> &nbsp;{E(f.rule)}<br>'
        f'<span class="sub">{E(f.detail)}</span><br>'
        f'<span class="cite">{E(f.citation)}</span></div>' for f in result.findings)

    clean = audit_letter(good, plain, charity.name, charity.ein)

    # 4. The four-gifts case.
    multi = {}
    for d in donations:
        multi.setdefault(d.donor_name, []).append(d)
    dana = max(multi.values(), key=len)
    summary = year_end_summary(charity, dana[0].donor_name, dana, dana[0].date.year)

    bad_list = "\n".join(f"  row {e.line}: {e.problem}" for e in bad_rows)

    body = f"""
<div class="wrap">
<header>
  <p class="eyebrow">IRC 170(f)(8) &middot; IRC 6115 &middot; IRS Publication 1771</p>
  <h1>Donor acknowledgment letters that survive an audit</h1>
  <p class="lede">A substantiation letter is a legal instrument. If it is missing a required
  sentence the donor's deduction can be disallowed, and the donor finds out years later, when the
  rule that the acknowledgment be contemporaneous means no corrected letter can help. This
  generates the letters, and audits the ones a charity already sent.</p>
</header>

<h2>The two thresholds are different rules</h2>
<p>They are constantly conflated, and they read differently in the statute. <b>$250 is
inclusive</b> and the duty is the donor's. <b>$75 is strict</b> and the duty, with a penalty
attached, is the charity's.</p>

<div class="grid">
  <div class="card"><span class="n">IRC 170(f)(8)</span><span class="k">$250</span>
    <p class="d"><b>or more.</b> Above this the donor cannot deduct without a contemporaneous
    written acknowledgment. Per contribution, not per year.</p></div>
  <div class="card"><span class="n">IRC 6115</span><span class="k">&gt; $75</span>
    <p class="d"><b>strictly above.</b> On a quid pro quo gift the charity must state that only
    the excess is deductible, and estimate what the donor received.</p></div>
  <div class="card"><span class="n">the common defect</span><span class="k">a negative</span>
    <p class="d">A $500 cash gift needs a sentence saying <b>no</b> goods or services were
    provided. The drafter has nothing to report, so reports nothing.</p></div>
</div>

<h2>Every case, decided</h2>
<p class="sub">Generated by running the tool over <code>corpus/donations.csv</code> at build time.
Nothing on this page is typed by hand.</p>
{donation_table}

<p>Read the two right-hand columns against each other. A <b>$100 gala ticket</b> owes a disclosure
and owes no acknowledgment. A <b>$300 cash gift</b> is the mirror image. <b>{E(dana[0].donor_name)}
gave {len(dana)} gifts totalling {money(sum(d.amount for d in dana))}</b> and owes neither, because
the rule counts contributions rather than years. Exactly $75 with goods received is outside 6115;
exactly $250 is inside 170(f)(8).</p>

<h2>The letter</h2>
<p>Highlighted: the two clauses that exist only because section 6115 applies. Below $75 they are
absent, and a tool that cannot tell those cases apart has the rule wrong.</p>
<div class="letter">{marked}</div>

<h2>The auditor reads text, not the objects that produced it</h2>
<p>This is the decision the project rests on. Checking the generator's own data structures would
confirm that two halves of one program agree, which they always will. Reading the finished letter
means the same auditor works on something written in Word by somebody who has never seen this
tool, and it means the audit can be run on text extracted back out of the <b>PDF</b>, which proves
the document a donor actually receives carries the required language.</p>

<div class="two">
  <div>
    <h3>The letter above, audited</h3>
    <div class="finding" style="border-left-color:var(--ok);background:var(--ok-soft)">
      <b>passes</b> &nbsp;{clean.checks_run} checks run, 0 findings
      <br><span class="sub">The count matters. "No findings" from an auditor that ran zero checks
      looks identical to a clean letter.</span></div>
  </div>
  <div>
    <h3>The same letter, two sentences removed</h3>
    {findings}
  </div>
</div>
<p class="sub">Findings are ordered by consequence, not by position in the document. A missing
goods-and-services statement can cost the donor everything; a missing EIN is untidy. Presenting
them as a flat list invites a charity to fix the easy one.</p>

<h2>Rows that cannot be used are reported, all of them, in one pass</h2>
<p>Including rows that parse cleanly and still cannot produce a letter. A reader that skips bad
rows silently generates 380 letters out of 400 and gives no sign that twenty donors got nothing.</p>
<pre>$ python3 -m donorack.cli letters --csv corpus/problem-rows.csv --charity corpus/charity.json --out out
{E(bad_list)}</pre>

<h2>The year-end summary is not a substitute</h2>
<p>The rule is per contribution. A summary listing a $300 gift among others does not become the
contemporaneous acknowledgment for it, so the goods-and-services statement repeats per line rather
than once at the bottom, and the document says plainly what it is not.</p>
<div class="letter">{E(summary)}</div>

<h2>What this does not prove</h2>
<div class="warn">
<p><b>That Publication 1771 says what both copies of the rules claim it says.</b> The package's
rules and the independent checker's rules were transcribed by the same author, and two
transcriptions by one author share a misreading. Every rule carries its citation so a reader can
check it rather than trust it.</p>
<p><b>That a letter passing the audit will survive an examination.</b> It carries the language the
publication requires. Facts, dates and amounts are the charity's to get right.</p>
<p style="margin-bottom:0"><b>This is not tax or legal advice.</b> A charity relying on it should
have its template reviewed by its own counsel, and every generated letter says so. The demo
charity's EIN uses prefix 00, which the IRS never issues, so it cannot collide with a real
organisation.</p>
</div>

<footer>
<p>No dependencies. Generating letters and PDFs needs nothing beyond the Python standard library;
the PDF writer emits the file by hand using the base fourteen fonts and the real Adobe AFM metrics
for Helvetica.</p>
<p><a href="https://github.com/JesseRWeigel/donor-acknowledgment-letters">Source, tests and the
verification harness on GitHub</a> &middot; built {datetime.date.today().isoformat()} &middot;
MIT</p>
</footer>
</div>
"""

    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Donor acknowledgment letters that survive an audit</title>
<meta name="description" content="Generate IRS-compliant donor acknowledgment letters from a
donation CSV, and audit the letters a charity already sent.">
<style>{CSS}</style>
</head><body>{body}</body></html>
"""
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"  wrote {out} ({len(page):,} bytes) from {len(donations)} donations, "
          f"{len(bad_rows)} rejected rows, {clean.checks_run} clean checks, "
          f"{len(result.findings)} demonstrated findings")
    if errors:
        print(f"  WARNING: the clean corpus has {len(errors)} unusable rows")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
