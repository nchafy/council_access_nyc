"""The load halves: how each kind of board source gets its bytes.

These used to live in `test_fetch.py` and monkeypatch the module's `_get`. They do not need
to any more: a loader is handed its getter in the `LoadRequest`, which is the seam the
registry exists to provide, so a test supplies a fake and nothing global is touched.
"""

from __future__ import annotations

import datetime
import json

import pytest

from showup.sources import board_loaders
from showup.sources.board_kinds import LoadError, LoadRequest
from showup.sources.board_loaders import load_pdf, load_plain, load_tribe

TODAY = datetime.date(2026, 11, 2)


def request(*urls: str, get, log=None, code: str = "207") -> LoadRequest:
    """A `LoadRequest` for one board, with a fake getter."""
    return LoadRequest(
        code=code,
        urls=tuple(urls),
        get=get,
        log=log if log is not None else (lambda _m: None),
        today=TODAY,
    )


def serving(pages: bytes, pdf: bytes = b"x" * 5_000):
    """A getter that answers `.page` URLs with `pages` and `.pdf` URLs with `pdf`."""

    def get(url, **_kwargs):
        return pdf if url.lower().split("?")[0].endswith(".pdf") else pages

    return get


def page_of(*hrefs: str | tuple[str, str]) -> bytes:
    """An HTML page linking each href, optionally with its own link text."""
    links = ""
    for href in hrefs:
        url, text = href if isinstance(href, tuple) else (href, "a month")
        links += f'<a href="{url}">{text}</a>'
    return f"<html><body>{links}</body></html>".encode()


def extracting(monkeypatch, extracted=None):
    """Stub the PDF text extraction, so these tests are about loading and not pypdf."""
    import showup.sources.board_pdf as board_pdf

    monkeypatch.setattr(
        board_pdf,
        "extract_pdf_text",
        lambda _data: (
            extracted
            if extracted is not None
            else {"layout": "grid", "plain": "OCTOBER 2026", "pages": "1"}
        ),
    )


class TestThePlainLoader:
    def test_it_returns_the_body_as_text(self):
        body = load_plain(request("https://www.nyc.gov/a.ics", get=lambda _u, **_k: b"BEGIN"))
        assert body == "BEGIN"

    def test_undecodable_bytes_do_not_raise(self):
        """These are third-party servers; a mislabelled encoding is their problem, and a
        replacement character is better than losing the whole board."""
        body = load_plain(request("https://www.nyc.gov/a.ics", get=lambda _u, **_k: b"\xff\xfe"))
        assert body


class TestTheTribeLoader:
    def test_it_asks_for_a_window_rather_than_upcoming(self):
        """Left to itself the endpoint defaults `start_date` to today and reports nothing,
        which is indistinguishable from a board with nothing scheduled. Brooklyn CB11 was
        recorded as publishing no events on exactly that basis and holds 79."""
        asked = []

        def get(url, **_kwargs):
            asked.append(url)
            return b'{"events": []}'

        load_tribe(request("https://b.org/wp-json/tribe/events/v1/events", get=get))
        assert asked == [
            "https://b.org/wp-json/tribe/events/v1/events"
            f"?per_page={board_loaders.TRIBE_PAGE}&start_date=2026-11-02"
        ]

    def test_a_query_already_on_the_url_is_replaced_not_appended(self):
        asked = []

        def get(url, **_kwargs):
            asked.append(url)
            return b"{}"

        load_tribe(request("https://b.org/events?per_page=5", get=get))
        assert asked[0].count("?") == 1
        assert asked[0] == (
            f"https://b.org/events?per_page={board_loaders.TRIBE_PAGE}&start_date=2026-11-02"
        )


class TestThePdfLoader:
    """Fifteen boards publish a schedule only as a PDF linked from a landing page, and six
    more publish a notice per meeting. The link has to be discovered, and the text is
    extracted at fetch time so that `data/` holds no binaries and the build stays offline.
    """

    LANDING = "https://www.nyc.gov/site/bronxcb7/calendar/calendar.page"

    def test_it_discovers_the_pdf_and_stores_the_extracted_text(self, monkeypatch):
        extracting(monkeypatch)
        body = load_pdf(
            request(self.LANDING, get=serving(page_of("/assets/bronxcb7/downloads/oct.pdf")))
        )
        [document] = json.loads(body)
        assert document["url"].endswith("/oct.pdf")
        assert document["plain"] == "OCTOBER 2026"

    def test_it_stores_no_pdf_bytes(self, monkeypatch):
        """The whole point of extracting at fetch time: a cache entry is text."""
        extracting(monkeypatch)
        body = load_pdf(request(self.LANDING, get=serving(page_of("/a/b/oct.pdf"))))
        assert "%PDF" not in body

    def test_a_relative_href_is_resolved_against_the_page(self, monkeypatch):
        extracting(monkeypatch)
        body = load_pdf(request(self.LANDING, get=serving(page_of("downloads/oct.pdf"))))
        assert json.loads(body)[0]["url"].startswith("https://www.nyc.gov/site/bronxcb7/")

    def test_a_link_to_another_host_is_not_followed(self, monkeypatch):
        """These pages are third-party HTML, so the href goes through the allowlist."""
        extracting(monkeypatch)
        with pytest.raises(LoadError, match="no PDF linked"):
            load_pdf(request(self.LANDING, get=serving(page_of("https://example.com/evil.pdf"))))

    def test_a_page_linking_no_pdf_is_a_failure(self, monkeypatch):
        extracting(monkeypatch)
        with pytest.raises(LoadError, match="no PDF linked"):
            load_pdf(request(self.LANDING, get=serving(page_of("/about.html"))))

    def test_the_same_pdf_linked_twice_is_fetched_once(self, monkeypatch):
        extracting(monkeypatch)
        body = load_pdf(request(self.LANDING, get=serving(page_of("/a/oct.pdf", "/a/oct.pdf"))))
        assert len(json.loads(body)) == 1

    def test_only_the_nearest_few_months_are_fetched(self, monkeypatch):
        """Bronx CB11 links every month through June 2027. The parsers drop what is past,
        so this only bounds an otherwise unbounded fetch."""
        extracting(monkeypatch)
        many = page_of(*[f"/a/{n}.pdf" for n in range(12)])
        body = load_pdf(request(self.LANDING, get=serving(many)))
        assert len(json.loads(body)) == board_loaders.BOARD_PDF_LIMIT

    def test_a_pdf_too_small_to_be_a_calendar_is_skipped(self, monkeypatch):
        """nyc.gov serves some error pages as `application/pdf`."""
        said = []
        extracting(monkeypatch)
        with pytest.raises(LoadError, match="yielded text"):
            load_pdf(
                request(
                    self.LANDING,
                    get=serving(page_of("/a/oct.pdf"), pdf=b"tiny"),
                    log=said.append,
                )
            )
        assert any("not a calendar" in line for line in said)

    def test_one_unfetchable_pdf_does_not_lose_the_others(self, monkeypatch):
        said = []
        extracting(monkeypatch, {"layout": "", "plain": "", "pages": "1"})

        def get(url, **_kwargs):
            if url.endswith("bad.pdf"):
                raise LoadError("gone")
            if url.lower().endswith(".pdf"):
                return b"x" * 5_000
            return page_of("/a/bad.pdf", "/a/good.pdf")

        body = load_pdf(request(self.LANDING, get=get, log=said.append))
        assert [d["url"] for d in json.loads(body)] == ["https://www.nyc.gov/a/good.pdf"]
        assert any("failed" in line for line in said)

    def test_a_document_pypdf_cannot_read_is_skipped_not_fatal(self, monkeypatch):
        """One malformed PDF must not take the other boards down with it."""
        said = []
        import showup.sources.board_pdf as board_pdf

        def explode(_data):
            raise ValueError("not a PDF at all")

        monkeypatch.setattr(board_pdf, "extract_pdf_text", explode)
        with pytest.raises(LoadError, match="yielded text"):
            load_pdf(request(self.LANDING, get=serving(page_of("/a/oct.pdf")), log=said.append))
        assert any("did not extract: ValueError" in line for line in said)

    def test_an_href_that_is_not_a_requestable_url_is_skipped_not_fatal(self, monkeypatch):
        """`http.client.InvalidURL` derives from `ValueError`, not `LoadError`. A board can
        link an href that cannot be requested, and that must not end the fetch."""
        said = []
        extracting(monkeypatch)

        def get(url, **_kwargs):
            if url.lower().endswith(".pdf"):
                raise ValueError("URL can't contain control characters")
            return page_of("/a/oct.pdf")

        with pytest.raises(LoadError, match="yielded text"):
            load_pdf(request(self.LANDING, get=get, log=said.append, code="203"))
        assert any("failed" in line for line in said)

    def test_a_board_may_keep_its_meetings_in_two_archives(self, monkeypatch):
        """Queens CB5 lists 53 board notices on one page and 331 committee notices on
        another. Reading only the first reports none of its committees."""
        extracting(monkeypatch, {"layout": "", "plain": "", "pages": "1"})

        def get(url, **_kwargs):
            if url.endswith("agendas.page"):
                return page_of(("/a/board-oct-2026.pdf", "October 14, 2026"))
            if url.endswith("notices.page"):
                return page_of(("/a/sanit-nov-2026.pdf", "November 4, 2026"))
            return b"x" * 5_000

        body = load_pdf(
            request(
                "https://www.nyc.gov/site/queenscb5/meetings/agendas.page",
                "https://www.nyc.gov/site/queenscb5/meetings/notices.page",
                get=get,
                code="405",
            )
        )
        assert [d["url"].rsplit("/", 1)[-1] for d in json.loads(body)] == [
            "board-oct-2026.pdf",
            "sanit-nov-2026.pdf",
        ]

    def test_the_same_pdf_linked_from_two_archives_is_fetched_once(self, monkeypatch):
        extracting(monkeypatch, {"layout": "", "plain": "", "pages": "1"})
        body = load_pdf(
            request(
                "https://www.nyc.gov/a/one.page",
                "https://www.nyc.gov/a/two.page",
                get=serving(page_of(("/a/oct.pdf", "October 2026"))),
                code="405",
            )
        )
        assert len(json.loads(body)) == 1

    def test_two_archives_that_link_nothing_name_both_in_the_failure(self):
        with pytest.raises(LoadError, match=r"one\.page, .*two\.page"):
            load_pdf(
                request(
                    "https://www.nyc.gov/a/one.page",
                    "https://www.nyc.gov/a/two.page",
                    get=lambda _u, **_k: b"<html>nothing</html>",
                    code="405",
                )
            )


class TestWhichPdfIsFetched:
    """`BOARD_PDF_LIMIT` truncates, so the order these links come back in decides which
    months a board contributes. Document order is not usable."""

    BASE = "https://www.nyc.gov/site/bronxcb11/meetings/calendar.page"

    def _links(self, *anchors, today=TODAY):
        return board_loaders._board_pdf_links(page_of(*anchors), self.BASE, today=today)

    def test_the_nearest_upcoming_month_comes_first(self):
        """Measured on Bronx CB11, whose page lists `meeting_preferences.pdf`, then
        `2023-09.pdf`, then `2027-06.pdf`, then `2027-05.pdf`. Taking the first four in
        document order got one file that is not a calendar, one three-year-old month and
        two in mid-2027 — and missed the November its readers needed."""
        found = self._links(
            ("/a/calendar/meeting_preferences.pdf", "Meeting preferences"),
            ("/a/calendar/2023-09.pdf", "September 2023"),
            ("/a/calendar/2027-06.pdf", "June 2027"),
            ("/a/calendar/2027-05.pdf", "May 2027"),
            ("/a/calendar/2026-11.pdf", "November 2026"),
            ("/a/calendar/2026-12.pdf", "December 2026"),
        )
        assert [href.rsplit("/", 1)[-1] for href in found[:4]] == [
            "2026-11.pdf",
            "2026-12.pdf",
            "2027-05.pdf",
            "2027-06.pdf",
        ]

    def test_the_current_month_still_counts_as_upcoming(self):
        """A board publishing only the current month must not be treated as past: there
        are usually meetings left in it."""
        found = self._links(("/a/2026-11.pdf", "November"), ("/a/2026-10.pdf", "October"))
        assert found[0].endswith("2026-11.pdf")

    def test_a_link_naming_no_month_is_tried_before_a_past_one(self):
        """A filename is not a convention — Bronx CB1 writes `-2026-CB1-Calendars-4.pdf`,
        which says nothing about which month it holds — so an unnamed link may well be
        the current calendar, and a 2018 one certainly is not."""
        found = self._links(
            ("/a/2018_general_meeting_schedule.pdf", "2018 schedule"),
            ("/a/-2026-CB1-Calendars-4.pdf", "Calendar"),
        )
        assert found[0].endswith("-2026-CB1-Calendars-4.pdf")

    def test_unnamed_links_keep_the_order_the_page_put_them_in(self):
        found = self._links(("/a/first.pdf", "one"), ("/a/second.pdf", "two"))
        assert [h.rsplit("/", 1)[-1] for h in found] == ["first.pdf", "second.pdf"]

    def test_past_months_come_back_most_recent_first(self):
        found = self._links(("/a/2026-05.pdf", "May"), ("/a/2026-09.pdf", "September"))
        assert [h.rsplit("/", 1)[-1] for h in found] == ["2026-09.pdf", "2026-05.pdf"]

    def test_a_link_naming_only_a_year_that_has_ended_sorts_last(self):
        """Queens CB12 keeps a `2018_general_meeting_schedule.pdf` beside its current
        calendar. A year that is over is enough to know the file is an archive."""
        found = self._links(
            ("/a/2018_general_meeting_schedule.pdf", "General meeting schedule"),
            ("/a/committee_meeting_schedule.pdf", "Committee meeting schedule"),
        )
        assert [h.rsplit("/", 1)[-1] for h in found] == [
            "committee_meeting_schedule.pdf",
            "2018_general_meeting_schedule.pdf",
        ]

    def test_a_link_naming_only_the_current_year_is_still_tried_early(self):
        found = self._links(
            ("/a/2026-09.pdf", "September 2026"),
            ("/a/-2026-CB1-Calendars-4.pdf", "Calendar"),
        )
        assert found[0].endswith("-2026-CB1-Calendars-4.pdf")

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("calendar/2026-11.pdf", (2026, 11)),
            ("calendar/2026_11.pdf", (2026, 11)),
            ("2026.10.01.pdf", (2026, 10)),
            ("October-2026-Calendar.pdf", (2026, 10)),
            ("november_2026.pdf", (2026, 11)),
            ("November2026Calendar.pdf", (2026, 11)),
            ("2026-September-Calendar.pdf", (2026, 9)),
            ("2026_April_Calendar.pdf", (2026, 4)),
            # `Month D, YYYY` and `MonD-YYYY`. Queens CB5 names its files the second way
            # and labels its links the first, and neither of the year-adjacent patterns
            # matches either — without this its 2015 and 2021 agendas outranked its 2026
            # ones and were the ones fetched.
            ("BoardMeetingNoticeOct14-2026.pdf", (2026, 10)),
            ("October 14, 2026 - Board Meeting", (2026, 10)),
            ("Agenda-for-March-2015.pdf March 11th, 2015", (2015, 3)),
            ("board-meeting-notice-september-14-2021.pdf", (2021, 9)),
            # `MMDDYYYY` run together, which is how Queens CB5 names most of its notices.
            # Nothing else matches it — the digits are flanked by other digits, so even the
            # bare-year pattern fails — and those files ranked as undated, which put the
            # board's 2021 notices ahead of its dated 2026 ones.
            ("AGENDA_CB5QBdMtg_12012021.pdf", (2021, 12)),
            ("CB5QBdMtg_07142021.pdf", (2021, 7)),
            # `MM.DD.YY`, which is how Brooklyn CB16 names its notices.
            ("10.27.26 AGENDA - GENERAL BOARD MEETING.pdf", (2026, 10)),
            # Not a date: a scanner's serial number, which Queens CB14 links.
            ("SKM_C36826101614370.pdf", None),
            ("calendar-202610.pdf", None),
            ("meeting_preferences.pdf", None),
            ("-2026-CB1-Calendars-4.pdf", None),
            ("2026-13.pdf", None),
        ],
    )
    def test_the_month_a_filename_names(self, text, expected):
        assert board_loaders._pdf_month(text) == expected

    def test_the_month_may_come_from_the_link_text_rather_than_the_href(self):
        found = self._links(("/a/20260127134946.pdf", "November 2026 calendar"))
        assert found == ["https://www.nyc.gov/a/20260127134946.pdf"]

    def test_the_link_text_is_believed_over_the_filename(self):
        """These filenames demonstrably lie: Queens CB5 publishes
        `ZoningHousingAugust2026.pdf` under a link reading `October 7, 2026`. Asking the
        filename first would file that notice two months early and drop it."""
        found = self._links(
            ("/a/ZoningHousingAugust2026.pdf", "November 7, 2026 - Zoning and Housing"),
            ("/a/NovemberCalendar2026.pdf", "August 3, 2026 - Parks"),
        )
        assert [h.rsplit("/", 1)[-1] for h in found] == [
            "ZoningHousingAugust2026.pdf",
            "NovemberCalendar2026.pdf",
        ]

    def test_the_citys_legacy_asset_host_is_followed(self):
        """Several board pages still emit asset links against `www1.nyc.gov`, which 301s
        to `www.nyc.gov`. 379 of the 648 PDF links across Queens CB5's two archive pages
        are `www1`, including every one of its 2026 notices — so rejecting the host meant
        that board's schedule could not be read at all."""
        href = "https://www1.nyc.gov/assets/queenscb5/downloads/pdf/agendas/oct-2026.pdf"
        assert self._links((href, "October 14, 2026")) == [href]

    def test_a_lookalike_of_that_host_is_still_refused(self):
        assert self._links(("https://www1.nyc.gov.evil.test/x.pdf", "October 2026")) == []

    def test_a_space_in_a_filename_is_encoded(self):
        """Bronx CB3 links `calendar/Committee Schedules.pdf`, with a literal space.
        `urllib` raises `InvalidURL` on that rather than encoding it, and the raise was
        neither a `LoadError` nor caught per link, so one board's filename took the whole
        board-calendar fetch down with it."""
        [href] = self._links(("/assets/bronxcb3/pdf/calendar/Committee Schedules.pdf", "x"))
        assert href.endswith("Committee%20Schedules.pdf")
        assert " " not in href

    def test_an_already_encoded_path_is_not_doubly_encoded(self):
        [href] = self._links(("/a/2026_February_Calendar%24.pdf", "February"))
        assert href.endswith("2026_February_Calendar%24.pdf")

    def test_a_query_string_survives_encoding(self):
        [href] = self._links(("/a/oct.pdf?v=2", "October"))
        assert href.endswith("oct.pdf?v=2")
