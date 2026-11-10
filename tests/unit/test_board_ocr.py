"""The two boards that publish their agendas only as scanned images.

Owner's instruction, 2026-11-02: install OCR.

**These tests do not run OCR.** The engine and its models are an optional extra, and the
suite must pass without them — a contributor who has not installed a 50 MB runtime still
has to be able to change this code. So the fixtures in `board_pdf_text.json` hold the text
OCR actually returned for both boards' live documents, and what is tested here is the two
things that are ours: the respacing of what the scan lost, and the refusal to publish a
date the model may have misread.

`tests/upstream` is where the engine itself would be exercised against a real PDF, under
the `upstream` marker that is excluded from CI.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from showup.sources.board_kinds import kind_for
from showup.sources.board_ocr import (
    OCR_PAGE_LIMIT,
    _respace,
    ocr_available,
    plausible_year,
)
from showup.sources.board_registry import install

install()

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "board_pdf_text.json"
DOCUMENTS = json.loads(FIXTURE.read_text(encoding="utf-8"))

#: Before the cutoff of both boards' captured notices.
CUTOFF = date(2025, 1, 1)


def read(code: str, *, on_or_after: date = CUTOFF):
    return kind_for("nyc-pdf-ocr").read(code, json.dumps(DOCUMENTS[code]), on_or_after)


class TestTheScannedBoards:
    def test_bronx_cb12_reads_its_one_sentence_notice(self):
        """`Thursday, April 23, 2026, at 7:00 P.M. in Town Hall 4101 White Plains Road` —
        the day, the hour and the venue in one line, with no labels at all."""
        found = {m.day: m for m in read("212")}
        assert set(found) == {date(2026, 4, 23), date(2026, 5, 28)}
        assert found[date(2026, 4, 23)].start_time == "7:00 PM"

    def test_queens_cb10_reads_a_notice_set_in_two_columns(self):
        """OCR returns each label and its value as separate lines, because they are
        separate text boxes: `DATE:` then `November 5, 2026` on the line after."""
        found = {m.day: m for m in read("410")}
        assert set(found) == {date(2026, 10, 1), date(2026, 11, 5)}
        assert found[date(2026, 11, 5)].start_time == "7:00 PM"
        assert found[date(2026, 11, 5)].location == "Old Mill Yacht Club"

    @pytest.mark.parametrize("code", ["212", "410"])
    def test_every_date_lands_on_the_weekday_the_board_meets(self, code):
        """Both boards meet on a Thursday. A misread digit in a scanned date is silent,
        and landing on the wrong weekday is the cheapest way to catch one."""
        for meeting in read(code):
            assert meeting.day.strftime("%a") == "Thu", (code, meeting.day)

    @pytest.mark.parametrize("code", ["212", "410"])
    def test_the_fixtures_are_text_not_images(self, code):
        """If these were empty the tests above would pass vacuously."""
        for document in DOCUMENTS[code]:
            assert len(document["plain"]) > 400

    @pytest.mark.parametrize("code", ["212", "410"])
    def test_layout_and_plain_are_the_same_for_a_scan(self, code):
        """OCR returns detected text boxes, not a rendering of the page's columns, so
        there is no column structure to preserve — which is why both these boards are
        configured as agenda boards rather than grids."""
        for document in DOCUMENTS[code]:
            assert document["layout"] == document["plain"]


class TestPuttingBackTheSpacesTheScanLost:
    @pytest.mark.parametrize(
        ("scanned", "expected"),
        [
            # The break that matters: this is where Queens CB10's date lives.
            ("November5,2026", "November 5,2026"),
            ("October1,2026", "October 1,2026"),
            # A venue.
            ("163-15CrossBayBlvd.", "163-15 Cross Bay Blvd."),
            ("OldMillYachtClub", "Old Mill Yacht Club"),
            # A heading, split from a closed vocabulary of the words a title is made of.
            ("REGULARBOARDMEETING", "REGULAR BOARD MEETING"),
            ("PUBLICHEARING", "PUBLIC HEARING"),
            # A combined line that lost its `at`.
            ("2026at", "2026 at"),
        ],
    )
    def test_it_breaks_where_the_scan_joined(self, scanned, expected):
        assert _respace(scanned) == expected

    @pytest.mark.parametrize("untouched", ["NYCHA", "COMMUNITYBOARD10", "11420", "203rd"])
    def test_it_leaves_alone_what_it_cannot_know(self, untouched):
        """A run of capitals that is not built from heading words stays as it is. Guessing
        at it would invent words that are not on the page — and `203rd` must not become
        `203 rd`."""
        assert _respace(untouched) == untouched

    def test_a_letterhead_misread_is_not_corrected(self):
        """`THECITYOFNEWYORKBoroughOfTheBron` is what the model returned. A letterhead is
        not load-bearing, and nothing here corrects a character the model got wrong."""
        assert "THECITYOFNEWYORK" in "".join(d["plain"] for d in DOCUMENTS["212"])


class TestRefusingADateTheModelMayHaveMisread:
    @pytest.mark.parametrize("year", [2015, 2026, 2035])
    def test_a_year_a_board_could_be_scheduling_is_kept(self, year):
        assert plausible_year(date(year, 6, 1))

    @pytest.mark.parametrize("year", [1926, 2014, 2036, 2062])
    def test_a_year_outside_the_window_is_dropped(self, year):
        """A scanned document is the one place a single misread digit silently becomes a
        different day — or a different decade — so it publishes nothing instead."""
        assert not plausible_year(date(year, 6, 1))

    def test_the_window_is_checked_on_the_parsed_date_not_on_the_text(self):
        """Filtering lines by the four-digit numbers in them was tried first and threw away
        the only line that mattered: Bronx CB12's notice reads "at 7:00 P.M. in Town Hall
        4101 White Plains Road", and `4101` is a street number, not a year."""
        assert any("4101" in document["plain"] for document in DOCUMENTS["212"])
        assert read("212")

    def test_an_implausible_date_is_dropped_by_the_ocr_reader(self):
        """The guard lives on the OCR kind's reader, not in the shared parser, so the
        twenty-one text boards are untouched by it."""
        envelope = json.dumps([{"plain": "DATE: Thursday, April 23, 2062\nTIME: 7:00 PM"}])
        assert kind_for("nyc-pdf-ocr").read("212", envelope, CUTOFF) == []
        assert kind_for("nyc-pdf").read("212", envelope, CUTOFF)


class TestTheCapabilityIsOptional:
    """`showup build` must not require a 50 MB runtime. A kind that cannot meet its
    `needs` fails its own boards and no others, which is the same contract a dead
    third-party site already has."""

    def test_the_kind_declares_what_it_needs(self):
        assert "ocr" in (kind_for("nyc-pdf-ocr").needs or "")

    def test_no_other_kind_needs_anything(self):
        """If a second kind ever declares a capability, the fetcher's handling of a
        missing one stops being exercised by this board alone."""
        from showup.sources.board_kinds import KINDS

        needy = {name for name, kind in KINDS.items() if kind.needs}
        assert needy == {"nyc-pdf-ocr", "browser"} or needy == {"nyc-pdf-ocr"}

    def test_without_the_extra_the_board_fails_and_says_how_to_fix_it(self, monkeypatch):
        import showup.sources.board_ocr as board_ocr
        from showup.sources.board_kinds import LoadError, LoadRequest
        from showup.sources.board_loaders import load_pdf_ocr

        monkeypatch.setattr(board_ocr, "ocr_available", lambda: False)
        request = LoadRequest(
            code="212",
            urls=("https://www.nyc.gov/site/bronxcb12/minutes/agendas.page",),
            get=lambda _u, **_k: b"",
            log=lambda _m: None,
            today=date(2026, 11, 2),
        )
        with pytest.raises(LoadError, match="extra ocr"):
            load_pdf_ocr(request)

    def test_reading_a_cached_body_never_needs_the_extra(self):
        """The whole point of caching text: a build parses what a fetch extracted, so only
        the machine that fetched needs OCR. Every test in this file relies on it."""
        assert read("212")

    def test_whether_the_extra_is_installed_is_reported_not_assumed(self):
        assert isinstance(ocr_available(), bool)

    def test_only_the_first_few_pages_of_a_document_are_read(self):
        """Bronx CB12's minutes run to 16 pages and its notices to 2. OCR is slow enough
        that reading a whole set of minutes to find nothing is a cost with no return."""
        assert OCR_PAGE_LIMIT <= 3


class FakePage:
    def __init__(self, boxes):
        self.boxes = boxes
        self.rendered_at = None

    def render(self, scale):
        self.rendered_at = scale
        return self

    def to_pil(self):
        return self

    def convert(self, _mode):
        return self


class FakeDocument:
    def __init__(self, pages):
        self.pages = pages

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]


def fake_engine(monkeypatch, pages):
    """Stand in for pypdfium2, rapidocr and numpy.

    The real engine is an optional extra, so the orchestration around it — how many pages
    are read, that the respacing is applied to what the model returns, that the envelope
    comes out in the shape the readers expect — is tested against fakes. Whether the model
    itself reads these documents is settled by the fixtures, which are its real output.
    """
    import sys
    import types

    import showup.sources.board_ocr as board_ocr

    document = FakeDocument([FakePage(boxes) for boxes in pages])

    pdfium = types.ModuleType("pypdfium2")
    pdfium.PdfDocument = lambda _data: document
    numpy = types.ModuleType("numpy")
    numpy.array = lambda image: image
    rapid = types.ModuleType("rapidocr_onnxruntime")

    class Engine:
        def __call__(self, image):
            return [(None, text) for text in image.boxes], 0.0

    rapid.RapidOCR = Engine

    monkeypatch.setitem(sys.modules, "pypdfium2", pdfium)
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", rapid)
    monkeypatch.setattr(board_ocr, "_ENGINE", None)
    return document


class TestTheExtraction:
    def test_it_returns_the_same_envelope_as_pypdf(self, monkeypatch):
        """The whole design rests on this: the per-board readers cannot tell whether the
        text came from pypdf or from OCR, so a scanned board is configured exactly like a
        text one."""
        from showup.sources.board_ocr import extract_ocr_text

        fake_engine(monkeypatch, [["DATE:", "November5,2026"]])
        envelope = extract_ocr_text(b"%PDF-fake")
        assert set(envelope) == {"layout", "plain", "pages"}
        assert envelope["pages"] == "1"

    def test_the_respacing_is_applied_to_what_the_model_returns(self, monkeypatch):
        from showup.sources.board_ocr import extract_ocr_text

        fake_engine(monkeypatch, [["REGULARBOARDMEETING", "November5,2026"]])
        assert "REGULAR BOARD MEETING" in extract_ocr_text(b"x")["plain"]

    def test_it_stops_after_the_page_limit(self, monkeypatch):
        """A set of minutes runs to 16 pages and holds no notice."""
        from showup.sources.board_ocr import OCR_PAGE_LIMIT, extract_ocr_text

        document = fake_engine(monkeypatch, [[f"page {n}"] for n in range(16)])
        envelope = extract_ocr_text(b"x")
        assert envelope["pages"] == "16", "the count is the whole document"
        read = [page for page in document.pages if page.rendered_at is not None]
        assert len(read) == OCR_PAGE_LIMIT

    def test_a_document_shorter_than_the_limit_is_read_whole(self, monkeypatch):
        from showup.sources.board_ocr import extract_ocr_text

        document = fake_engine(monkeypatch, [["one"], ["two"]])
        extract_ocr_text(b"x")
        assert all(page.rendered_at is not None for page in document.pages)

    def test_it_renders_large_enough_to_read_the_small_print(self, monkeypatch):
        """Scale 1 loses the smaller print on Queens CB10's notices."""
        from showup.sources.board_ocr import OCR_SCALE, extract_ocr_text

        document = fake_engine(monkeypatch, [["x"]])
        extract_ocr_text(b"x")
        assert document.pages[0].rendered_at == OCR_SCALE > 1

    def test_a_page_the_model_finds_nothing_on_is_not_an_error(self, monkeypatch):
        from showup.sources.board_ocr import extract_ocr_text

        fake_engine(monkeypatch, [[]])
        assert extract_ocr_text(b"x")["plain"] == ""

    def test_the_engine_is_built_once(self, monkeypatch):
        """Loading the models costs about a second, and a fetch reads many documents."""
        import showup.sources.board_ocr as board_ocr

        fake_engine(monkeypatch, [["x"]])
        board_ocr.extract_ocr_text(b"x")
        first = board_ocr._ENGINE
        board_ocr.extract_ocr_text(b"x")
        assert board_ocr._ENGINE is first

    def test_availability_is_false_when_the_extra_is_absent(self, monkeypatch):
        import builtins

        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name in ("pypdfium2", "rapidocr_onnxruntime"):
                raise ImportError(name)
            return real(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)
        assert ocr_available() is False
