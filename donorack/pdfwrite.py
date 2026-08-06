"""A PDF writer in the standard library, because the alternative is worse.

A charity that wants to run this on its own machine should not have to install a rendering stack,
and an acknowledgment letter is one column of black text on white paper. So this emits the PDF by
hand using the base fourteen fonts, which every reader has and none of which need embedding.

THE WIDTHS ARE NOT GUESSED. Line breaking has to know how wide each character is. A writer that
assumes one width for everything runs capital W off the page and ends a line of lowercase i early.
The tables below are the Adobe AFM metrics for Helvetica, in 1/1000 em.
`scripts/check_independent.py` compares every entry against the copy that ships inside pdfminer,
so a transcription error is caught rather than shipped. That check proves the table matches
Adobe's published metrics. It does not prove Adobe is right, and nothing here pretends otherwise.

Text is encoded WinAnsi (cp1252), which is what /WinAnsiEncoding means, and a character outside it
raises rather than being dropped or replaced. A donor's name quietly losing a letter on a document
they file with their tax return is not an acceptable fallback.
"""
from __future__ import annotations

import dataclasses
import zlib

PAGE_WIDTH = 612.0    # US Letter, in points
PAGE_HEIGHT = 792.0
MARGIN = 72.0         # one inch
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN

HELVETICA = {
    32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191, 40: 333, 41: 333, 42:
    389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278, 48: 556, 49: 556, 50: 556, 51: 556, 52: 556,
    53: 556, 54: 556, 55: 556, 56: 556, 57: 556, 58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63:
    556, 64: 1015, 65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778, 72: 722, 73:
    278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778, 80: 667, 81: 778, 82: 722, 83: 667,
    84: 611, 85: 722, 86: 667, 87: 944, 88: 667, 89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94:
    469, 95: 556, 96: 333, 97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556, 104:
    556, 105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556, 111: 556, 112: 556, 113: 556,
    114: 333, 115: 500, 116: 278, 117: 556, 118: 500, 119: 722, 120: 500, 121: 500, 122: 500, 123:
    334, 124: 260, 125: 334, 126: 584, 161: 333, 162: 556, 163: 556, 164: 556, 165: 556, 166: 260,
    167: 556, 168: 333, 169: 737, 170: 370, 171: 556, 172: 584, 174: 737, 175: 333, 176: 400, 177:
    584, 178: 333, 179: 333, 180: 333, 181: 556, 182: 537, 183: 278, 184: 333, 185: 333, 186: 365,
    187: 556, 188: 834, 189: 834, 190: 834, 191: 611, 192: 667, 193: 667, 194: 667, 195: 667, 196:
    667, 197: 667, 198: 1000, 199: 722, 200: 667, 201: 667, 202: 667, 203: 667, 204: 278, 205:
    278, 206: 278, 207: 278, 208: 722, 209: 722, 210: 778, 211: 778, 212: 778, 213: 778, 214: 778,
    215: 584, 216: 778, 217: 722, 218: 722, 219: 722, 220: 722, 221: 667, 222: 667, 223: 611, 224:
    556, 225: 556, 226: 556, 227: 556, 228: 556, 229: 556, 230: 889, 231: 500, 232: 556, 233: 556,
    234: 556, 235: 556, 236: 278, 237: 278, 238: 278, 239: 278, 240: 556, 241: 556, 242: 556, 243:
    556, 244: 556, 245: 556, 246: 556, 247: 584, 248: 611, 249: 556, 250: 556, 251: 556, 252: 556,
    253: 500, 254: 556, 255: 500
}
HELVETICA_BOLD = {
    32: 278, 33: 333, 34: 474, 35: 556, 36: 556, 37: 889, 38: 722, 39: 238, 40: 333, 41: 333, 42:
    389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278, 48: 556, 49: 556, 50: 556, 51: 556, 52: 556,
    53: 556, 54: 556, 55: 556, 56: 556, 57: 556, 58: 333, 59: 333, 60: 584, 61: 584, 62: 584, 63:
    611, 64: 975, 65: 722, 66: 722, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778, 72: 722, 73: 278,
    74: 556, 75: 722, 76: 611, 77: 833, 78: 722, 79: 778, 80: 667, 81: 778, 82: 722, 83: 667, 84:
    611, 85: 722, 86: 667, 87: 944, 88: 667, 89: 667, 90: 611, 91: 333, 92: 278, 93: 333, 94: 584,
    95: 556, 96: 333, 97: 556, 98: 611, 99: 556, 100: 611, 101: 556, 102: 333, 103: 611, 104: 611,
    105: 278, 106: 278, 107: 556, 108: 278, 109: 889, 110: 611, 111: 611, 112: 611, 113: 611, 114:
    389, 115: 556, 116: 333, 117: 611, 118: 556, 119: 778, 120: 556, 121: 556, 122: 500, 123: 389,
    124: 280, 125: 389, 126: 584, 161: 333, 162: 556, 163: 556, 164: 556, 165: 556, 166: 280, 167:
    556, 168: 333, 169: 737, 170: 370, 171: 556, 172: 584, 174: 737, 175: 333, 176: 400, 177: 584,
    178: 333, 179: 333, 180: 333, 181: 611, 182: 556, 183: 278, 184: 333, 185: 333, 186: 365, 187:
    556, 188: 834, 189: 834, 190: 834, 191: 611, 192: 722, 193: 722, 194: 722, 195: 722, 196: 722,
    197: 722, 198: 1000, 199: 722, 200: 667, 201: 667, 202: 667, 203: 667, 204: 278, 205: 278,
    206: 278, 207: 278, 208: 722, 209: 722, 210: 778, 211: 778, 212: 778, 213: 778, 214: 778, 215:
    584, 216: 778, 217: 722, 218: 722, 219: 722, 220: 722, 221: 667, 222: 667, 223: 611, 224: 556,
    225: 556, 226: 556, 227: 556, 228: 556, 229: 556, 230: 889, 231: 556, 232: 556, 233: 556, 234:
    556, 235: 556, 236: 278, 237: 278, 238: 278, 239: 278, 240: 611, 241: 611, 242: 611, 243: 611,
    244: 611, 245: 611, 246: 611, 247: 584, 248: 611, 249: 611, 250: 611, 251: 611, 252: 611, 253:
    556, 254: 611, 255: 556
}
WIDTHS = {"Helvetica": HELVETICA, "Helvetica-Bold": HELVETICA_BOLD}


class PdfEncodingError(ValueError):
    """A character the base fourteen fonts cannot represent."""


def encode(text: str) -> bytes:
    """WinAnsi bytes, or an error naming the character that will not fit."""
    try:
        return text.encode("cp1252")
    except UnicodeEncodeError as e:
        bad = text[e.start:e.end]
        raise PdfEncodingError(
            f"{bad!r} (U+{ord(bad[0]):04X}) has no place in WinAnsiEncoding, so it cannot be "
            f"written with the base fourteen fonts. Substituting or dropping it would alter a "
            f"name on a tax document, so this refuses instead."
        ) from e


def width_of(text: str, font: str = "Helvetica", size: float = 11.0) -> float:
    """The width of a string in points, from the real metrics.

    Adobe's table has no entry for the unassigned WinAnsi slots. A character arriving here without
    a width means the caller skipped the encoding step, so this raises instead of guessing an
    average, which would put the wrapping quietly out by a few points per line.
    """
    table = WIDTHS[font]
    total = 0
    for ch in text:
        w = table.get(ord(ch))
        if w is None:
            raise PdfEncodingError(f"{ch!r} (U+{ord(ch):04X}) has no width in {font}")
        total += w
    return total * size / 1000.0


def wrap(text: str, font: str = "Helvetica", size: float = 11.0,
         limit: float = TEXT_WIDTH) -> list[str]:
    """Greedy line breaking on real widths.

    A word wider than the whole column is broken rather than allowed to run into the margin. That
    happens with a long URL or an unspaced account number, and letting it overflow means the end
    of it is simply not on the paper.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        line = ""
        for word in paragraph.split(" "):
            while width_of(word, font, size) > limit:
                cut = len(word)
                while cut > 1 and width_of(word[:cut] + "-", font, size) > limit:
                    cut -= 1
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:cut] + "-")
                word = word[cut:]
            candidate = f"{line} {word}" if line else word
            if line and width_of(candidate, font, size) > limit:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def _escape(raw: bytes) -> bytes:
    for a, b in ((b"\\", b"\\\\"), (b"(", b"\\("), (b")", b"\\)")):
        raw = raw.replace(a, b)
    return raw


@dataclasses.dataclass
class Line:
    text: str
    font: str = "Helvetica"
    size: float = 11.0
    leading: float = 15.0


def paginate(lines: list[Line], top: float = PAGE_HEIGHT - MARGIN,
             bottom: float = MARGIN) -> list[list[tuple[float, Line]]]:
    """Split lines into pages, each line paired with the baseline it sits on."""
    pages: list[list[tuple[float, Line]]] = []
    page: list[tuple[float, Line]] = []
    y = top
    for line in lines:
        y -= line.leading
        if y < bottom:
            pages.append(page)
            page = []
            y = top - line.leading
        page.append((y, line))
    pages.append(page)
    return pages


def _content(page: list[tuple[float, Line]]) -> bytes:
    parts = [b"BT"]
    current = None
    for y, line in page:
        key = (line.font, line.size)
        if key != current:
            res = b"/F1" if line.font == "Helvetica" else b"/F2"
            parts.append(res + b" " + f"{line.size:g}".encode("ascii") + b" Tf")
            current = key
        parts.append(b"1 0 0 1 " + f"{MARGIN:g} {y:.2f}".encode("ascii") + b" Tm")
        if line.text:
            parts.append(b"(" + _escape(encode(line.text)) + b") Tj")
    parts.append(b"ET")
    return b"\n".join(parts)


def render(lines: list[Line], title: str = "", compress: bool = True) -> bytes:
    """A complete PDF file as bytes."""
    pages = paginate(lines)
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                       b"/Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                    b"/Encoding /WinAnsiEncoding >>")
    resources = (b"<< /Font << /F1 " + str(font_regular).encode() + b" 0 R /F2 "
                 + str(font_bold).encode() + b" 0 R >> >>")

    # Reserved now so each page can name its parent, filled once the kids are known.
    pages_id = len(objects) + 1
    objects.append(b"")

    kids = []
    for page in pages:
        raw = _content(page)
        if compress:
            stream, extra = zlib.compress(raw), b" /Filter /FlateDecode"
        else:
            stream, extra = raw, b""
        content_id = add(b"<< /Length " + str(len(stream)).encode() + extra
                         + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = add(b"<< /Type /Page /Parent " + str(pages_id).encode()
                      + b" 0 R /MediaBox [0 0 " + f"{PAGE_WIDTH:g} {PAGE_HEIGHT:g}".encode()
                      + b"] /Resources " + resources + b" /Contents "
                      + str(content_id).encode() + b" 0 R >>")
        kids.append(page_id)

    objects[pages_id - 1] = (b"<< /Type /Pages /Count " + str(len(kids)).encode() + b" /Kids ["
                             + b" ".join(str(k).encode() + b" 0 R" for k in kids) + b"] >>")
    catalog = add(b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>")
    info = add(b"<< /Title (" + _escape(encode(title)) + b") /Producer (donorack) >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root "
            + str(catalog).encode() + b" 0 R /Info " + str(info).encode()
            + b" 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n")
    return bytes(out)


def letter_pdf(text: str, title: str = "") -> bytes:
    """A composed letter as a PDF, wrapped to the column.

    The blocks arrive already separated by blank lines because `letter.compose` joins named
    clauses that way, so the paragraph structure survives into the PDF instead of being inferred.
    """
    lines: list[Line] = []
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        if block.strip() == "---":
            lines.append(Line("", leading=10.0))
            continue
        for piece in wrap(block):
            lines.append(Line(piece))
        lines.append(Line("", leading=8.0))
    return render(lines, title=title)
