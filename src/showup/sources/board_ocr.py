"""Reading the boards that publish their agendas only as scanned images.

Two boards do: Bronx CB12 (58 agenda and minutes PDFs) and Queens CB10 (65 agendas). Every
one is a photograph of a page — pypdf extracts zero characters from all of them — so there
is nothing to parse until something has looked at the pixels.

**This produces the same envelope as `extract_pdf_text`**: `{layout, plain, pages}`. That
is the point. The per-board readers in `board_pdf.py` do not know or care whether the text
came from pypdf or from OCR, so a scanned board is configured exactly like a text one and
every refusal and quirk already written down applies unchanged.

Owner's instruction, 2026-11-02: install OCR. It is an **optional extra**, not a runtime
dependency — `pyproject.toml` puts it under `[project.optional-dependencies] ocr` — because
it is two orders of magnitude heavier than anything else here and `showup build` must not
require it. A machine without it fails these two boards and no others, which is the same
contract a dead third-party site already has.

## What OCR gets wrong, and what is done about it

It drops spaces in condensed text. Measured on both boards' live documents: Queens CB10's
date comes out as `November5,2026` and its venue as `163-15CrossBayBlvd.`, while the body
prose of Bronx CB12's notice keeps its spaces. The date is in the condensed part on exactly
the board where that matters, so `_respace` puts the spaces back at the boundaries where
they were lost. It is narrow on purpose: between a month name and a digit, and between a
digit and a following capitalised word. A general "split every letter-digit boundary" would
also shred `115-01LEFFERTSBOULEVARD` into something no worse but no better, and would put a
space inside `203rd`.

Nothing here corrects a *character* OCR misread. `THECITYOFNEWYORKBoroughOfTheBron` is what
the model returned for a letterhead and it stays that way: a letterhead is not load-bearing,
and a model that misreads a digit in a date is a reason to publish nothing for that
document, not a reason to guess. `_plausible` is what enforces that.
"""

from __future__ import annotations

import re
from datetime import date

__all__ = ["OCR_SCALE", "extract_ocr_text", "ocr_available"]

#: How much to magnify the page before looking at it. 2 is about 144 dpi, which reads these
#: documents and costs ~2.5 s a page; 1 loses the smaller print on Queens CB10's notices.
OCR_SCALE = 2

#: How many pages of one document to read. A board's notice is on the first page or two,
#: and OCR is slow enough that reading a 16-page set of minutes to find nothing is a cost
#: with no return. Bronx CB12's minutes run to 16 pages; its notices are 2.
OCR_PAGE_LIMIT = 3

_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"

#: `November5` — a month name against a digit, which is the break that matters.
_MONTH_DIGIT = re.compile(rf"\b({_MONTHS})(\d)", re.I)

#: `163-15CrossBay` — a digit against a capitalised word.
_DIGIT_WORD = re.compile(r"(\d)([A-Z][a-z]{2,})")

#: `2026at` — a year against a lowercase word, which is how a combined line loses its `at`.
_YEAR_WORD = re.compile(r"(20\d\d)([a-z]{2,})")

#: `OldMillYachtClub`, `CrossBayBlvd` — a lowercase letter against a capital. These are
#: venues, and the board did not write them that way; the spaces were lost in the scan.
#: Left alone for runs of capitals, so `NYCHA` and `COMMUNITYBOARD10` are not disturbed.
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")

#: The words a board's heading is made of, for splitting a run of capitals that the scan
#: joined: `REGULARBOARDMEETING` is how Queens CB10's heading arrives. A closed vocabulary
#: rather than a dictionary, because the only runs worth splitting are the ones a title is
#: built from, and guessing at the rest would invent words that are not on the page.
_CAPS_WORDS = (
    "REGULAR",
    "SPECIAL",
    "ANNUAL",
    "GENERAL",
    "FULL",
    "BOARD",
    "PUBLIC",
    "HEARING",
    "MEETING",
    "COMMITTEE",
    "EXECUTIVE",
    "CABINET",
)
_CAPS_RUN = re.compile(r"\b(?:" + "|".join(_CAPS_WORDS) + r"){2,}\b")
_CAPS_WORD = re.compile("|".join(_CAPS_WORDS))


def ocr_available() -> bool:
    """Whether the optional OCR extra is installed."""
    try:
        import pypdfium2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _respace(text: str) -> str:
    """Put back the spaces OCR drops in condensed print. See the module docstring."""
    text = _MONTH_DIGIT.sub(r"\1 \2", text)
    text = _DIGIT_WORD.sub(r"\1 \2", text)
    text = _YEAR_WORD.sub(r"\1 \2", text)
    text = _CAPS_RUN.sub(lambda run: " ".join(_CAPS_WORD.findall(run.group())), text)
    return _CAMEL.sub(" ", text)


#: The window a date read off a scan has to fall in. A scanned document is the one place a
#: single misread digit silently becomes a different day, so a year outside this is treated
#: as a misread and the document publishes nothing.
#:
#: Checked against the **parsed date**, never against the text. Filtering lines by the
#: four-digit numbers in them was tried first and threw away the only line that mattered:
#: Bronx CB12's notice reads "Thursday, April 23, 2026, at 7:00 P.M. in Town Hall 4101
#: White Plains Road", and `4101` is a street number.
_EARLIEST_PLAUSIBLE_YEAR = 2015
_LATEST_PLAUSIBLE_YEAR = 2035


def _reader():
    """The OCR engine, built once per process. Loading its models costs about a second."""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    return _ENGINE


_ENGINE = None


def extract_ocr_text(data: bytes) -> dict[str, str]:
    """One scanned PDF as text, in the same envelope `extract_pdf_text` returns.

    `layout` and `plain` are the same string here. OCR returns detected text boxes, not a
    rendering of the page's columns, so there is no column structure to preserve and
    nothing for a grid reader to work with — which is why both boards that need this are
    configured as agenda boards, where the date is in the text rather than in a position.
    """
    import numpy
    import pypdfium2

    engine = _reader()
    document = pypdfium2.PdfDocument(data)
    pages = len(document)

    lines: list[str] = []
    for index in range(min(pages, OCR_PAGE_LIMIT)):
        image = document[index].render(scale=OCR_SCALE).to_pil().convert("RGB")
        found, _elapsed = engine(numpy.array(image))
        for box in found or []:
            line = _respace(str(box[1]).strip())
            if line:
                lines.append(line)

    text = "\n".join(lines)
    return {"layout": text, "plain": text, "pages": str(pages)}


def plausible_year(day: date) -> bool:
    """Whether a date read off a scan is one worth publishing."""
    return _EARLIEST_PLAUSIBLE_YEAR <= day.year <= _LATEST_PLAUSIBLE_YEAR
