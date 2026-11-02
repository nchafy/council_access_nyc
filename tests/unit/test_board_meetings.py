"""The boards' own calendars: three feed shapes, and the refusals around them.

The fixture carries a real trimmed sample of each shape — Google Calendar ICS, a board's
own ICS, The Events Calendar's REST response, and Manhattan CB7's bespoke JSON — so the
parsers are tested against the genuine article rather than against something written to
match them. Ten synthetic tribe feeds pad it to clear the ingest floors without committing
a megabyte of other people's prose.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from showup.sources.board_meetings import (
    BOARD_FEED_FLOOR,
    BOARD_MEETING_FLOOR,
    BoardMeetingsError,
    load_board_meetings,
    parse_feed,
    parse_ics,
    parse_mcb7,
    parse_tribe,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "board_meetings.json"
DAY = date(2026, 9, 22)


@pytest.fixture(scope="module")
def cached() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loaded() -> dict:
    return load_board_meetings(FIXTURE, on_or_after=DAY)


class TestTheRealFeeds:
    @pytest.mark.parametrize(
        ("code", "kind"),
        [("308", "gcal-ics"), ("112", "other-ics"), ("101", "tribe"), ("107", "other-json")],
    )
    def test_each_shape_yields_dated_entries(self, loaded, code, kind):
        entries = loaded[code]
        assert entries, (code, kind)
        for entry in entries:
            assert entry.day >= DAY
            assert entry.title

    def test_a_google_calendar_entry_keeps_its_venue(self, loaded):
        """The venue is the thing the City publishes nowhere, so it is the point."""
        assert any(entry.location for entry in loaded["308"])

    def test_times_are_local_not_utc(self, loaded):
        """Google writes these in UTC with a `Z`. Converted wrong, a 6 pm meeting reads as
        the small hours of the next day — and subtracting with `replace(hour=...)` throws
        outright on anything before 05:00Z, which killed every ICS feed once."""
        evening = [e for e in loaded["308"] if e.start_time and e.start_time.endswith("PM")]
        assert evening, [e.start_time for e in loaded["308"]]

    def test_entries_are_ordered_by_day(self, loaded):
        for entries in loaded.values():
            assert [e.day for e in entries] == sorted(e.day for e in entries)

    def test_a_dead_feed_is_absent_rather_than_empty(self, loaded, cached):
        """Board 999's feed failed. It must not appear at all: an empty list would render
        as "this board has no meetings", which is a different and false claim."""
        assert cached["feeds"]["999"]["body"] is None
        assert "999" not in loaded

    def test_the_fixture_clears_both_floors(self, loaded):
        assert len(loaded) >= BOARD_FEED_FLOOR
        assert sum(len(v) for v in loaded.values()) >= BOARD_MEETING_FLOOR


class TestTheIcsReader:
    def test_a_folded_line_is_rejoined(self):
        """iCalendar wraps at 75 octets with a leading space. Unjoined, a venue is cut."""
        body = (
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:20261112T230000Z\r\n"
            "SUMMARY:Full Board Meeting\r\nLOCATION:Brooklyn Children's Museum\\, 145 Brookly\r\n"
            " n Avenue\\, Brooklyn\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        [entry] = parse_ics(body, on_or_after=DAY)
        assert entry.location == "Brooklyn Children's Museum, 145 Brooklyn Avenue, Brooklyn"

    def test_an_all_day_entry_has_no_time(self):
        body = (
            "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261112\r\nSUMMARY:Office closed\r\nEND:VEVENT\r\n"
        )
        [entry] = parse_ics(body, on_or_after=DAY)
        assert entry.day == date(2026, 11, 12)
        assert entry.start_time is None

    @pytest.mark.parametrize(
        ("dtstart", "expected_day", "expected_time"),
        [
            # 23:00Z in November is 18:00 in New York, which is UTC-5 then.
            ("DTSTART:20261112T230000Z", date(2026, 11, 12), "6:00 PM"),
            # 22:30Z in July is 18:30, daylight saving being in force. Dated 2027 so it
            # is ahead of the cutoff; July 2026 is behind it and correctly dropped.
            ("DTSTART:20270715T223000Z", date(2027, 7, 15), "6:30 PM"),
            # An early-UTC entry crosses midnight backwards into the previous day.
            ("DTSTART:20261113T003000Z", date(2026, 11, 12), "7:30 PM"),
            # No trailing Z means the calendar already wrote local time.
            ("DTSTART;TZID=America/New_York:20261112T183000", date(2026, 11, 12), "6:30 PM"),
        ],
    )
    def test_utc_entries_land_on_the_right_evening(self, dtstart, expected_day, expected_time):
        body = f"BEGIN:VEVENT\r\n{dtstart}\r\nSUMMARY:Meeting\r\nEND:VEVENT\r\n"
        [entry] = parse_ics(body, on_or_after=DAY)
        assert (entry.day, entry.start_time) == (expected_day, expected_time)

    def test_past_entries_are_dropped(self):
        body = (
            "BEGIN:VEVENT\r\nDTSTART:20150305T183000\r\nSUMMARY:Old\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nDTSTART:20261112T183000\r\nSUMMARY:New\r\nEND:VEVENT\r\n"
        )
        assert [e.title for e in parse_ics(body, on_or_after=DAY)] == ["New"]

    def test_an_undated_entry_is_dropped_rather_than_guessed(self):
        body = "BEGIN:VEVENT\r\nSUMMARY:No date at all\r\nEND:VEVENT\r\n"
        assert parse_ics(body, on_or_after=DAY) == []

    def test_an_unparseable_dtstart_is_dropped(self):
        body = "BEGIN:VEVENT\r\nDTSTART:not-a-date\r\nSUMMARY:Broken\r\nEND:VEVENT\r\n"
        assert parse_ics(body, on_or_after=DAY) == []

    def test_an_entry_with_no_summary_still_renders_as_something(self):
        body = "BEGIN:VEVENT\r\nDTSTART:20261112T183000\r\nEND:VEVENT\r\n"
        [entry] = parse_ics(body, on_or_after=DAY)
        assert entry.title == "Meeting"

    def test_markup_in_a_summary_does_not_survive(self):
        """These feeds are third-party prose, which is the one thing this project treats as
        hostile by default (CLAUDE.md)."""
        body = (
            "BEGIN:VEVENT\r\nDTSTART:20261112T183000\r\n"
            "SUMMARY:<script>alert(1)</script>Parks Committee\r\nEND:VEVENT\r\n"
        )
        [entry] = parse_ics(body, on_or_after=DAY)
        assert "<" not in entry.title
        assert "script" not in entry.title.lower()


class TestTheTribeReader:
    def test_entities_in_a_title_are_resolved(self):
        """Tribe returns titles HTML-encoded: "Licensing &#038; Permits"."""
        payload = {
            "events": [
                {
                    "start_date": "2026-11-02 18:00:00",
                    "title": "Licensing &#038; Permits Committee",
                    "all_day": False,
                    "url": "https://example.gov/e",
                    "venue": {},
                }
            ]
        }
        [entry] = parse_tribe(payload, on_or_after=DAY)
        assert entry.title == "Licensing & Permits Committee"

    def test_an_all_day_event_has_no_time(self):
        payload = {
            "events": [
                {"start_date": "2026-11-02 00:00:00", "title": "Street fair", "all_day": True}
            ]
        }
        [entry] = parse_tribe(payload, on_or_after=DAY)
        assert entry.start_time is None

    def test_a_venue_falls_back_to_its_address(self):
        payload = {
            "events": [
                {
                    "start_date": "2026-11-02 18:00:00",
                    "title": "Meeting",
                    "venue": {"venue": None, "address": "250 Broadway"},
                }
            ]
        }
        [entry] = parse_tribe(payload, on_or_after=DAY)
        assert entry.location == "250 Broadway"

    def test_an_unparseable_start_is_dropped(self):
        payload = {"events": [{"start_date": "soon", "title": "Meeting"}]}
        assert parse_tribe(payload, on_or_after=DAY) == []

    def test_no_events_key_is_not_an_error(self):
        assert parse_tribe({}, on_or_after=DAY) == []


class TestTheBespokeReader:
    def test_it_reads_date_time_and_location(self):
        payload = [
            {
                "title": "Executive Committee",
                "date": "2026-11-02",
                "time": "4:00 PM",
                "location": "250 West 87th Street",
                "agendaUrl": "https://example.gov/a",
            }
        ]
        [entry] = parse_mcb7(payload, on_or_after=DAY)
        assert (entry.day, entry.start_time, entry.location) == (
            date(2026, 11, 2),
            "4:00 PM",
            "250 West 87th Street",
        )

    def test_a_committee_stands_in_for_a_missing_title(self):
        payload = [{"committee": "Parks Committee", "date": "2026-11-02"}]
        [entry] = parse_mcb7(payload, on_or_after=DAY)
        assert entry.title == "Parks Committee"

    def test_an_unparseable_date_is_dropped(self):
        assert parse_mcb7([{"title": "Meeting", "date": "sometime"}], on_or_after=DAY) == []

    def test_an_empty_payload_is_not_an_error(self):
        assert parse_mcb7([], on_or_after=DAY) == []


class TestTheDispatchAndTheFloors:
    def test_an_unknown_kind_is_refused(self):
        with pytest.raises(BoardMeetingsError, match="unknown feed kind"):
            parse_feed("carrier-pigeon", "{}", on_or_after=DAY)

    def test_unparseable_json_is_refused(self):
        with pytest.raises(BoardMeetingsError, match="not valid JSON"):
            parse_feed("tribe", "{oh no", on_or_after=DAY)

    def test_a_tribe_array_is_refused(self):
        with pytest.raises(BoardMeetingsError, match="expected an object"):
            parse_feed("tribe", "[]", on_or_after=DAY)

    def test_a_bespoke_object_is_refused(self):
        with pytest.raises(BoardMeetingsError, match="expected an array"):
            parse_feed("other-json", "{}", on_or_after=DAY)

    def test_a_missing_cache_is_refused(self, tmp_path):
        with pytest.raises(BoardMeetingsError, match="No such file"):
            load_board_meetings(tmp_path / "absent.json", on_or_after=DAY)

    def test_a_json_array_cache_is_refused(self, tmp_path):
        path = tmp_path / "bm.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(BoardMeetingsError, match="expected an object"):
            load_board_meetings(path, on_or_after=DAY)

    def test_a_thin_ingest_is_refused(self, tmp_path, cached):
        """One board answering is a broken ingest, not a quiet week."""
        path = tmp_path / "bm.json"
        path.write_text(json.dumps({"feeds": {"101": cached["feeds"]["101"]}}), encoding="utf-8")
        with pytest.raises(BoardMeetingsError, match="floor is"):
            load_board_meetings(path, on_or_after=DAY)

    def test_a_feed_that_will_not_parse_is_skipped_not_fatal(self, tmp_path, cached):
        """A third-party site changing shape must not take the other 22 down with it."""
        feeds = dict(cached["feeds"])
        feeds["101"] = {"kind": "tribe", "url": "u", "body": "{not json"}
        path = tmp_path / "bm.json"
        path.write_text(json.dumps({"feeds": feeds}), encoding="utf-8")
        loaded = load_board_meetings(path, on_or_after=DAY)
        assert "101" not in loaded
        assert len(loaded) >= BOARD_FEED_FLOOR

    def test_an_entry_that_is_not_a_dict_is_skipped(self, tmp_path, cached):
        feeds = dict(cached["feeds"])
        feeds["103"] = "not a dict"
        path = tmp_path / "bm.json"
        path.write_text(json.dumps({"feeds": feeds}), encoding="utf-8")
        assert "103" not in load_board_meetings(path, on_or_after=DAY)


class TestWhatItRefusesToClaim:
    """A board calendar carries none of what a council hearing's record carries."""

    def test_a_board_meeting_has_no_attendance_mode_or_deadline(self, loaded):
        entry = loaded["308"][0]
        for invented in ("attendance_mode", "written_safe_until", "topic", "time_state"):
            assert not hasattr(entry, invented), invented


class TestTheRemainingBranches:
    def test_a_date_only_dtstart_without_the_value_param(self):
        """Some calendars write `DTSTART:20261112` with no `VALUE=DATE`, which falls
        through the datetime parse to the date-only one."""
        body = "BEGIN:VEVENT\r\nDTSTART:20261112\r\nSUMMARY:All day\r\nEND:VEVENT\r\n"
        [entry] = parse_ics(body, on_or_after=DAY)
        assert (entry.day, entry.start_time) == (date(2026, 11, 12), None)

    def test_a_date_only_dtstart_that_is_nonsense_is_dropped(self):
        body = "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261399\r\nSUMMARY:x\r\nEND:VEVENT\r\n"
        assert parse_ics(body, on_or_after=DAY) == []

    def test_a_past_tribe_event_is_dropped(self):
        payload = {"events": [{"start_date": "2020-01-01 18:00:00", "title": "Old"}]}
        assert parse_tribe(payload, on_or_after=DAY) == []

    def test_a_past_bespoke_entry_is_dropped(self):
        assert parse_mcb7([{"title": "Old", "date": "2020-01-01"}], on_or_after=DAY) == []

    def test_too_few_boards_answering_is_refused_even_with_enough_meetings(self, tmp_path):
        """The two floors catch different failures. Three boards publishing 110 entries
        each clears the meeting floor and is still not the city's boards answering."""
        import datetime

        base = datetime.date(2026, 11, 1)
        events = [
            {
                "start_date": (base + datetime.timedelta(days=n)).isoformat() + " 18:30:00",
                "title": f"Committee {n}",
                "all_day": False,
            }
            for n in range(110)
        ]
        feeds = {
            str(code): {"kind": "tribe", "url": "u", "body": json.dumps({"events": events})}
            for code in (101, 102, 103)
        }
        path = tmp_path / "bm.json"
        path.write_text(json.dumps({"feeds": feeds}), encoding="utf-8")
        with pytest.raises(BoardMeetingsError, match="boards answered, floor is"):
            load_board_meetings(path, on_or_after=DAY)


class TestThePublishedShape:
    """`site/data/board-meetings.json` is a contract: a separate backend reads it, so its
    field types must not vary between boards."""

    def _payload(self, boards: dict) -> dict:
        from datetime import datetime

        from showup.render import board_schedule_payload

        return board_schedule_payload(
            {},
            {"boards": boards, "caveat": "c", "statuses": {}},
            today=DAY,
            built_at=datetime(2026, 11, 2, 12, 0, 0),
        )

    def test_source_url_is_a_string_even_for_a_board_with_two_archives(self):
        """Queens CB5 declares two archive pages. Emitting a list for that board and a
        string for the other 58 would make every consumer special-case it."""
        payload = self._payload(
            {
                "405": {
                    "label": "Queens CB5",
                    "kind": "nyc-pdf",
                    "url": ["https://a", "https://b"],
                },
                "409": {"label": "Queens CB9", "kind": "nyc-pdf", "url": "https://c"},
            }
        )
        for code in ("405", "409"):
            assert isinstance(payload["boards"][code]["source_url"], str), code
        assert payload["boards"]["405"]["other_source_urls"] == ["https://b"]
        assert payload["boards"]["409"]["other_source_urls"] is None

    def test_a_board_with_no_source_says_so_rather_than_being_absent(self):
        """A consumer must be able to tell "no meetings scheduled" from "we cannot read
        this board", which a list of only the working boards destroys."""
        payload = self._payload({"105": {"label": "Manhattan CB5", "status": "blocked"}})
        assert payload["boards"]["105"]["source_url"] is None
        assert payload["coverage"]["with_a_readable_source"] == 0

    def test_several_archives_count_once_towards_coverage(self):
        payload = self._payload({"405": {"label": "Queens CB5", "url": ["https://a", "https://b"]}})
        assert payload["coverage"]["with_a_readable_source"] == 1


class TestSourceFreshness:
    """Two signals per board, because they answer different questions.

    `fetched_at` says when we last looked. `latest_entry` says when the *board* last said
    anything. A source fetched this morning whose newest meeting is eight months old is
    stale, and only the second shows it; a board with nothing upcoming but a meeting last
    week is simply between meetings.
    """

    def _cache(self, tmp_path, feeds: dict):
        path = tmp_path / "bm.json"
        path.write_text(json.dumps({"feeds": feeds}), encoding="utf-8")
        return path

    def _ics(self, *stamps: str) -> str:
        events = "".join(
            f"BEGIN:VEVENT\r\nDTSTART:{s}T183000\r\nSUMMARY:Meeting\r\nEND:VEVENT\r\n"
            for s in stamps
        )
        return f"BEGIN:VCALENDAR\r\n{events}END:VCALENDAR\r\n"

    def test_it_reports_the_newest_date_a_source_states(self, tmp_path):
        """Past dates count. The question is whether the board is still publishing, not
        whether it has something coming up."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(
            tmp_path,
            {"301": {"kind": "gcal-ics", "body": self._ics("20260115", "20260520")}},
        )
        found = source_freshness(path, today=date(2026, 11, 2))
        assert found["301"].latest_entry == date(2026, 5, 20)
        assert found["301"].stale_days == 166

    def test_a_source_publishing_ahead_is_current_not_negatively_stale(self, tmp_path):
        """Manhattan CB7 posts a continuous schedule into 2029 — 193 entries in 2028
        alone, which was checked rather than assumed. "Stale -1011 days" says nothing a
        reader wants, so it floors at zero."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(tmp_path, {"107": {"kind": "gcal-ics", "body": self._ics("20290809")}})
        found = source_freshness(path, today=date(2026, 11, 2))
        assert found["107"].latest_entry == date(2029, 8, 9)
        assert found["107"].stale_days == 0

    def test_a_source_that_states_no_date_has_no_staleness(self, tmp_path):
        """Brooklyn CB11's feed answers and holds nothing. That is a different fact from
        being behind, and a number would imply one."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(tmp_path, {"311": {"kind": "tribe", "body": '{"events": []}'}})
        found = source_freshness(path, today=date(2026, 11, 2))
        assert found["311"].loaded is True
        assert found["311"].latest_entry is None
        assert found["311"].stale_days is None

    def test_a_failed_load_is_not_an_empty_source(self, tmp_path):
        """The distinction this project is most careful not to conflate: "we could not read
        this board" against "the board published nothing"."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(tmp_path, {"105": {"kind": "nyc-html", "body": None, "error": "403"}})
        found = source_freshness(path, today=date(2026, 11, 2))
        assert found["105"].loaded is False
        assert found["105"].latest_entry is None

    def test_it_carries_the_time_that_board_was_last_loaded(self, tmp_path):
        """Stamped per board rather than once per run, so a board whose load fails keeps
        the time of its last success."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(
            tmp_path,
            {
                "301": {
                    "kind": "gcal-ics",
                    "body": self._ics("20261112"),
                    "fetched_at": "2026-11-02T09:00:00",
                }
            },
        )
        assert source_freshness(path, today=date(2026, 11, 2))["301"].fetched_at == (
            "2026-11-02T09:00:00"
        )

    def test_every_kind_is_measured_the_same_way(self, tmp_path, cached):
        """The newest date is obtained by calling each kind's own `read` with an early
        cutoff — the same call for a feed, a PDF, an OCR'd scan and a rendered page — so no
        kind carries staleness code of its own. That is what the registry is for."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(tmp_path, cached["feeds"])
        found = source_freshness(path, today=date(2026, 11, 2))
        assert len(found) == len(cached["feeds"])
        measured = [c for c, f in found.items() if f.latest_entry]
        assert measured, "the fixture's real feeds should all state a date"

    def test_a_cache_that_is_not_an_object_is_refused(self, tmp_path):
        from showup.sources.board_meetings import BoardMeetingsError, source_freshness

        path = tmp_path / "bm.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(BoardMeetingsError, match="expected an object"):
            source_freshness(path, today=DAY)

    def test_a_source_that_will_not_parse_is_measured_as_stating_nothing(self, tmp_path):
        """A format change must not take the staleness report down with it."""
        from showup.sources.board_meetings import source_freshness

        path = self._cache(tmp_path, {"101": {"kind": "tribe", "body": "{not json"}})
        assert source_freshness(path, today=DAY)["101"].latest_entry is None


class TestTheSourceHealthTable:
    """Aggregate plus exceptions, not fifty-nine rows: a page listing every board as "fine"
    buries the four that are not, and this page has a weight budget."""

    def _health(self, boards: dict, freshness: dict | None = None):
        from showup.render import board_source_health

        return board_source_health({"boards": boards}, freshness or {})

    def _fresh(self, **kwargs):
        from showup.sources.board_meetings import SourceFreshness

        return SourceFreshness(
            **{"loaded": True, "fetched_at": None, "latest_entry": None, "stale_days": None}
            | kwargs
        )

    def test_a_current_board_is_not_listed(self):
        """Only what a maintainer would act on."""
        health = self._health(
            {"101": {"label": "MCB1", "kind": "tribe", "fetched": True}},
            {"101": self._fresh(latest_entry=date(2026, 12, 1), stale_days=0)},
        )
        assert health is None, "an empty table is not rendered at all"

    def test_a_board_behind_the_window_is_listed_with_how_far(self):
        health = self._health(
            {"312": {"label": "BKCB12", "kind": "nyc-pdf", "fetched": True}},
            {"312": self._fresh(latest_entry=date(2025, 5, 27), stale_days=524)},
        )
        assert health["rows"] == [["BKCB12", "nyc-pdf", "27 May 2025", "524 days behind"]]

    def test_a_board_just_inside_the_window_is_not_listed(self):
        from showup.render import SOURCE_BEHIND_DAYS

        health = self._health(
            {"203": {"label": "BXCB3", "kind": "nyc-pdf", "fetched": True}},
            {"203": self._fresh(latest_entry=date(2026, 9, 1), stale_days=SOURCE_BEHIND_DAYS)},
        )
        assert health is None

    @pytest.mark.parametrize(
        ("board", "freshness", "expected"),
        [
            # Four causes that look identical in a naive table and are not.
            ({"fetched": False, "status": "blocked"}, None, ("Not readable", "blocked")),
            ({"fetched": True}, "absent", ("Not yet fetched", "wired since the last fetch")),
            ({"fetched": True}, {"loaded": False}, ("Could not be read", "last load failed")),
            ({"fetched": True}, {"loaded": True}, ("Nothing dated", "answers, but states no date")),
        ],
    )
    def test_each_cause_of_silence_reads_differently(self, board, freshness, expected):
        """ "We could not read this board" and "the board published nothing" are different
        facts, and saying the second when the first is true blames the board for our gap."""
        fresh = {} if freshness == "absent" else {"999": self._fresh(**(freshness or {}))}
        health = self._health({"999": {"label": "Board", "kind": "x", **board}}, fresh)
        assert tuple(health["rows"][0][2:]) == expected

    def test_an_unreadable_board_shows_no_kind(self):
        health = self._health({"105": {"label": "MCB5", "fetched": False, "status": "blocked"}})
        assert health["rows"][0][1] == "—"

    def test_the_table_uses_the_shared_spec_shape(self):
        """The same spec the map panel renders, so there is one notion of a table here."""
        health = self._health(
            {"105": {"label": "MCB5", "fetched": False, "status": "blocked"}},
        )
        assert set(health) == {"legend", "columns", "rows", "caption", "href"}
        assert len(health["columns"]) == len(health["rows"][0])

    def test_boards_are_listed_in_code_order(self):
        health = self._health(
            {
                "312": {"label": "BKCB12", "fetched": False, "status": "x"},
                "105": {"label": "MCB5", "fetched": False, "status": "y"},
            }
        )
        assert [row[0] for row in health["rows"]] == ["MCB5", "BKCB12"]
