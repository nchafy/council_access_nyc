"""The fetch stage, tested without touching the network.

What matters is not that urllib works but that a bad response can never replace a good
cache entry, so every fetcher is substituted. One network test is marked `upstream`.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from showup.fetch import SOURCES, FetchError, fetch_all, fetch_one

CALENDAR = next(s for s in SOURCES if s.name == "calendar")
GOOD_CALENDAR = b'<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00">' + b"x" * 300_000


def _source(name: str):
    return next(s for s in SOURCES if s.name == name)


def _returning(source, body: bytes):
    """A copy of `source` whose fetcher returns `body`."""
    return replace(source, fetch=lambda log: body)


class TestFailClosed:
    def test_a_good_body_is_written(self, tmp_path):
        assert (
            fetch_one(_returning(CALENDAR, GOOD_CALENDAR), tmp_path, log=lambda m: None)
            == "fetched"
        )
        assert (tmp_path / CALENDAR.filename).read_bytes() == GOOD_CALENDAR

    def test_a_short_body_is_refused(self, tmp_path):
        with pytest.raises(FetchError, match="floor is"):
            fetch_one(_returning(CALENDAR, b"too short"), tmp_path, log=lambda m: None)
        assert not (tmp_path / CALENDAR.filename).exists()

    def test_an_error_page_served_as_200_is_refused(self, tmp_path):
        """The case this design exists for: Legistar returns HTTP 200 with an error body,
        so only a body invariant catches it."""
        error_page = b"<html><title>Invalid feed</title></html>" + b"y" * 300_000
        with pytest.raises(FetchError, match="calendar grid"):
            fetch_one(_returning(CALENDAR, error_page), tmp_path, log=lambda m: None)

    def test_a_bad_fetch_leaves_the_previous_copy_untouched(self, tmp_path):
        target = tmp_path / CALENDAR.filename
        target.write_bytes(GOOD_CALENDAR)

        with pytest.raises(FetchError):
            fetch_one(_returning(CALENDAR, b"nope"), tmp_path, log=lambda m: None)

        assert target.read_bytes() == GOOD_CALENDAR, "a failed fetch destroyed the cache"

    def test_no_partial_file_is_left_behind(self, tmp_path):
        with pytest.raises(FetchError):
            fetch_one(_returning(CALENDAR, b"nope"), tmp_path, log=lambda m: None)
        assert not list(tmp_path.glob("*.part"))


class TestInvariants:
    def test_socrata_error_object_is_caught(self, tmp_path):
        members = _source("members")
        body = json.dumps({"error": True, "message": "invalid SoQL"}).encode() + b" " * 60_000
        with pytest.raises(FetchError, match="Socrata error"):
            fetch_one(_returning(members, body), tmp_path, log=lambda m: None)

    def test_too_few_rows_is_caught(self, tmp_path):
        members = _source("members")
        body = json.dumps([{"name": "x"}] * 10).encode() + b" " * 60_000
        with pytest.raises(FetchError, match="rows, floor is"):
            fetch_one(_returning(members, body), tmp_path, log=lambda m: None)

    def test_wrong_geojson_feature_count_is_caught(self, tmp_path):
        geometry = _source("council-geometry")
        # 50 features, not 51: a boundary change, or a truncated export.
        body = (
            json.dumps(
                {"type": "FeatureCollection", "features": [{"properties": {}} for _ in range(50)]}
            ).encode()
            + b" " * 1_100_000
        )
        with pytest.raises(FetchError, match="50 features, expected exactly 51"):
            fetch_one(_returning(geometry, body), tmp_path, log=lambda m: None)

    def test_incomplete_district_scrape_is_caught(self, tmp_path):
        districts = _source("districts")
        pages = {str(n): f"<h1>District {n}</h1>" + "z" * 30_000 for n in range(1, 40)}
        with pytest.raises(FetchError, match="of 51 district pages"):
            fetch_one(
                _returning(districts, json.dumps(pages).encode()), tmp_path, log=lambda m: None
            )

    def test_51_pages_of_the_wrong_thing_is_caught(self, tmp_path):
        """51 copies of a login wall would clear the count and the size floor."""
        districts = _source("districts")
        pages = {str(n): "<h1>Sign in to continue</h1>" + "z" * 30_000 for n in range(1, 52)}
        with pytest.raises(FetchError, match="does not contain its own heading"):
            fetch_one(
                _returning(districts, json.dumps(pages).encode()), tmp_path, log=lambda m: None
            )


class TestFreshness:
    def test_a_fresh_copy_is_skipped(self, tmp_path, monkeypatch):
        (tmp_path / CALENDAR.filename).write_bytes(GOOD_CALENDAR)

        called = []
        monkeypatch.setattr(
            "showup.fetch.SOURCES",
            (replace(CALENDAR, fetch=lambda log: called.append(1) or GOOD_CALENDAR),),
        )
        report = fetch_all(tmp_path, log=lambda m: None)
        assert report["sources"]["calendar"]["status"] == "fresh"
        assert not called, "a fresh source was fetched anyway"

    def test_force_refetches_a_fresh_copy(self, tmp_path, monkeypatch):
        (tmp_path / CALENDAR.filename).write_bytes(GOOD_CALENDAR)
        called = []
        monkeypatch.setattr(
            "showup.fetch.SOURCES",
            (replace(CALENDAR, fetch=lambda log: called.append(1) or GOOD_CALENDAR),),
        )
        report = fetch_all(tmp_path, force=True, log=lambda m: None)
        assert report["sources"]["calendar"]["status"] == "fetched"
        assert called

    def test_a_stale_copy_is_refetched(self, tmp_path, monkeypatch):
        import os
        import time

        target = tmp_path / CALENDAR.filename
        target.write_bytes(b"old")
        # Older than the calendar's 12-hour window.
        old = time.time() - 48 * 3600
        os.utime(target, (old, old))

        monkeypatch.setattr(
            "showup.fetch.SOURCES", (replace(CALENDAR, fetch=lambda log: GOOD_CALENDAR),)
        )
        report = fetch_all(tmp_path, log=lambda m: None)
        assert report["sources"]["calendar"]["status"] == "fetched"
        assert target.read_bytes() == GOOD_CALENDAR


class TestFetchAll:
    def test_one_failure_does_not_stop_the_others(self, tmp_path, monkeypatch):
        """A dead source must not block the rest: the build's own floors catch a partly
        refreshed cache, and aborting would let one flaky host block every refresh."""

        def boom(log):
            raise FetchError("upstream is down")

        monkeypatch.setattr(
            "showup.fetch.SOURCES",
            (
                replace(CALENDAR, name="first", filename="first.html", fetch=boom),
                replace(CALENDAR, name="second", filename="second.html"),
            ),
        )
        report = fetch_all(tmp_path, force=True, log=lambda m: None)
        assert report["sources"]["first"]["status"] == "failed"
        assert report["sources"]["second"]["status"] == "fetched"
        assert report["failed"] == ["first"]

    def test_unknown_source_name_is_rejected(self, tmp_path):
        with pytest.raises(FetchError, match="unknown source"):
            fetch_all(tmp_path, only="not-a-source", log=lambda m: None)

    def test_only_fetches_one_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "showup.fetch.SOURCES",
            (
                replace(CALENDAR, name="a", filename="a.html"),
                replace(CALENDAR, name="b", filename="b.html"),
            ),
        )
        report = fetch_all(tmp_path, only="a", force=True, log=lambda m: None)
        assert set(report["sources"]) == {"a"}


class TestPoliteness:
    def test_every_scraped_host_has_a_declared_delay(self):
        """Politeness is a per-host decision and must be explicit.

        council.nyc.gov publishes Crawl-delay: 10, data.cityofnewyork.us 1, and
        nyc.legistar.com no robots.txt at all, so its 2 s is our choice, not a permission.
        """
        from showup.fetch import CRAWL_DELAY

        assert CRAWL_DELAY["council.nyc.gov"] >= 10.0, "council.nyc.gov asks for 10 s"
        assert CRAWL_DELAY["data.cityofnewyork.us"] >= 1.0
        assert CRAWL_DELAY["nyc.legistar.com"] >= 1.0

    def test_the_user_agent_identifies_the_project(self):
        from showup.fetch import USER_AGENT

        # A city sysadmin who wants to complain should be able to find us.
        assert "showup" in USER_AGENT.lower()
        assert "github.com" in USER_AGENT


@pytest.mark.upstream
class TestAgainstRealHosts:
    """Contract tests. Excluded from CI so a third party cannot redden the build."""

    def test_calendar_still_has_its_grid(self):
        from showup.fetch import _fetch_calendar

        body = _fetch_calendar(lambda m: None)
        assert b"gridCalendar" in body
        assert len(body) > 200_000

    def test_council_robots_still_asks_for_ten_seconds(self):
        """If the City raises its crawl delay, we must follow it."""
        import urllib.request

        from showup.fetch import CRAWL_DELAY, USER_AGENT

        request = urllib.request.Request(
            "https://council.nyc.gov/robots.txt", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            robots = response.read().decode("utf-8", "replace")
        declared = [
            float(line.split(":", 1)[1])
            for line in robots.splitlines()
            if line.lower().startswith("crawl-delay")
        ]
        assert declared, "council.nyc.gov no longer publishes a Crawl-delay"
        assert CRAWL_DELAY["council.nyc.gov"] >= max(declared), (
            f"robots.txt now asks for {max(declared)} s; our delay is "
            f"{CRAWL_DELAY['council.nyc.gov']} s"
        )


class TestHttpLayer:
    """`_get`, `_fetch_calendar` and the Socrata pager, with urlopen substituted.

    Retry, failover and paging only run when something upstream has already gone wrong, so
    they are the least likely code to be exercised by accident.
    """

    @staticmethod
    def _fake_urlopen(responses, calls=None):
        """A urlopen stand-in yielding each response in turn: bytes for a 200, or an
        exception instance to raise."""
        import io

        queue = list(responses)

        class _Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        def fake(request, timeout=None):
            if calls is not None:
                calls.append(request.full_url)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return _Response(item)

        return fake

    def test_retries_a_server_error_then_succeeds(self, monkeypatch):
        import urllib.error

        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen(
                [
                    urllib.error.HTTPError("u", 503, "busy", {}, None),
                    b"second attempt",
                ]
            ),
        )
        assert fetch_module._get("https://example.gov/x") == b"second attempt"

    def test_does_not_retry_a_404(self, monkeypatch):
        import urllib.error

        from showup import fetch as fetch_module

        calls: list[str] = []
        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([urllib.error.HTTPError("u", 404, "gone", {}, None)] * 4, calls),
        )
        with pytest.raises(FetchError, match="not retryable"):
            fetch_module._get("https://example.gov/missing")
        assert len(calls) == 1

    def test_gives_up_after_the_retry_budget(self, monkeypatch):
        import urllib.error

        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([urllib.error.URLError("no route")] * 4),
        )
        with pytest.raises(FetchError, match="failed after 4 attempts"):
            fetch_module._get("https://example.gov/x")

    def test_calendar_falls_over_to_the_second_host(self, monkeypatch):
        """The failover exists because it was verified byte-identical, not hoped at."""
        from showup import fetch as fetch_module

        calls: list[str] = []
        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([b"an error page, no grid here", GOOD_CALENDAR], calls),
        )
        messages: list[str] = []
        body = fetch_module._fetch_calendar(messages.append)
        assert b"gridCalendar" in body
        assert "legistar.council.nyc.gov" in calls[1]
        assert any("failover" in m for m in messages), "the failover was not reported"

    def test_calendar_raises_when_both_hosts_are_useless(self, monkeypatch):
        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([b"no grid", b"also no grid"]),
        )
        with pytest.raises(FetchError, match="neither Legistar host"):
            fetch_module._fetch_calendar(lambda m: None)

    def test_socrata_pager_follows_pages_and_orders_stably(self, monkeypatch):
        from showup import fetch as fetch_module

        calls: list[str] = []
        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        # Two full pages then a short one, which is how the loop knows to stop.
        page_one = json.dumps([{"i": n} for n in range(3)]).encode()
        page_two = json.dumps([{"i": n} for n in range(3, 5)]).encode()
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([page_one, page_two], calls),
        )
        fetcher = fetch_module._socrata_rows("abcd-1234", "i", page=3)
        rows = json.loads(fetcher(lambda m: None))
        assert [r["i"] for r in rows] == [0, 1, 2, 3, 4]
        # Without a stable sort Socrata gives no ordering guarantee, so rows duplicate or
        # vanish between pages.
        assert "%24order=%3Aid" in calls[0]
        assert "%24offset=3" in calls[1]

    def test_socrata_error_object_raises_rather_than_being_stored(self, monkeypatch):
        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._fake_urlopen([json.dumps({"error": True, "message": "bad SoQL"}).encode()]),
        )
        fetcher = fetch_module._socrata_rows("abcd-1234", "i")
        with pytest.raises(FetchError, match="Socrata error"):
            fetcher(lambda m: None)

    def test_polite_wait_actually_waits(self, monkeypatch):
        from showup import fetch as fetch_module

        slept: list[float] = []
        monkeypatch.setattr(fetch_module.time, "sleep", slept.append)
        clock = iter([100.0, 100.0, 100.5])
        monkeypatch.setattr(fetch_module.time, "monotonic", lambda: next(clock))
        fetch_module._last_request.clear()

        fetch_module._polite_wait("council.nyc.gov")  # first call: no wait
        fetch_module._polite_wait("council.nyc.gov")  # 0.5 s later: must wait ~9.5 s
        assert slept and 9.0 < slept[0] <= 10.0, slept


def _budget_rows(*, pairs: int = 59, per_board: int = 52, publication: str = "20260630"):
    """A payload shaped like `vn4m-mk4t`: one publication, every board, past the floor."""
    boros = ["1", "2", "3", "4", "5"]
    rows = []
    for index in range(pairs):
        boro = boros[index % 5]
        board = f"{index // 5 + 1:02d}"
        for priority in range(per_board):
            rows.append(
                {
                    "publication": publication,
                    "boro": boro,
                    "board": board,
                    "priority": f"{priority % 25 + 1:02d}",
                    "tracking_code": f"{boro}{board}2027{priority:02d}C",
                    "request": "Reconstruct or upgrade a park",
                    "explanation": "x" * 200,
                    "response": "OMB supports the agency's position as follows:",
                    "responded_by": "OMB",
                    "responsible_agency": "Department of Parks and Recreation",
                }
            )
    return rows


class TestBudgetRegisterInvariant:
    """`vn4m-mk4t` is cached one publication at a time, so the invariant proves the payload
    is that dataset, covers all 59 boards, and carries exactly one publication — a `$where`
    that silently stopped filtering looks fine."""

    @staticmethod
    def _invariant(body: bytes):
        return _source("budget-requests").invariant(body)

    def _check(self, rows):
        return self._invariant(json.dumps(rows).encode())

    def test_a_real_shaped_payload_passes(self):
        assert self._check(_budget_rows()) is None

    def test_too_few_rows_is_caught(self):
        assert "floor is" in self._check(_budget_rows(per_board=2))

    def test_a_payload_missing_a_column_is_not_this_dataset(self):
        rows = _budget_rows()
        for row in rows:
            del row["responsible_agency"]
        assert "responsible_agency" in self._check(rows)

    def test_fewer_than_59_boards_is_caught(self):
        assert "58 boro/board pairs" in self._check(_budget_rows(pairs=58, per_board=60))

    def test_two_publications_in_one_payload_is_caught(self):
        rows = _budget_rows() + _budget_rows(publication="20270217")
        assert "2 publications" in self._check(rows)

    def test_malformed_json_is_named_as_such(self):
        assert "not valid JSON" in self._invariant(b"{oh dear")

    def test_a_socrata_error_object_is_caught(self):
        body = json.dumps({"error": True, "message": "invalid SoQL"}).encode()
        assert "Socrata error" in self._invariant(body)

    def test_an_object_where_an_array_is_expected_is_caught(self):
        assert "expected a JSON array" in self._invariant(b'{"a": 1}')

    def test_the_size_floor_refuses_a_thin_payload(self, tmp_path):
        with pytest.raises(FetchError, match="floor is"):
            fetch_one(
                _returning(_source("budget-requests"), json.dumps(_budget_rows()[:5]).encode()),
                tmp_path,
                log=lambda m: None,
            )
        assert not (tmp_path / "board_budget_requests.json").exists()

    def test_a_good_payload_replaces_the_cache_entry(self, tmp_path):
        body = json.dumps(_budget_rows()).encode()
        assert len(body) > _source("budget-requests").min_bytes
        fetch_one(_returning(_source("budget-requests"), body), tmp_path, log=lambda m: None)
        assert (tmp_path / "board_budget_requests.json").read_bytes() == body


class TestBudgetRegisterPublicationChoice:
    """The newest publication is dated in the future, so the fetcher must not ask for it."""

    @staticmethod
    def _urlopen(bodies, calls):
        import io

        queue = list(bodies)

        class _Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        def fake(request, timeout=None):
            calls.append(request.full_url)
            return _Response(queue.pop(0))

        return fake

    @staticmethod
    def _editions(*stamps):
        return json.dumps([{"publication": stamp} for stamp in stamps]).encode()

    def test_it_skips_a_future_edition_and_says_so(self, monkeypatch):
        from datetime import date

        from showup import fetch as fetch_module

        calls: list[str] = []
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._urlopen([self._editions("20270217", "20260630", "20260512")], calls),
        )
        messages: list[str] = []
        chosen = fetch_module._published_not_in_the_future(messages.append, date(2026, 9, 30))
        assert chosen == "20260630"
        assert any("20270217" in message for message in messages)

    def test_a_register_with_nothing_in_the_past_fails_closed(self, monkeypatch):
        from datetime import date

        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._urlopen([self._editions("20270217")], []),
        )
        with pytest.raises(FetchError, match="no publication on or before"):
            fetch_module._published_not_in_the_future(lambda m: None, date(2026, 9, 30))

    def test_a_socrata_error_on_the_edition_query_fails_closed(self, monkeypatch):
        from datetime import date

        from showup import fetch as fetch_module

        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._urlopen([json.dumps({"error": True}).encode()], []),
        )
        with pytest.raises(FetchError, match="Socrata error"):
            fetch_module._published_not_in_the_future(lambda m: None, date(2026, 9, 30))

    def test_the_row_query_asks_for_one_publication_and_a_limit_above_3809(self, monkeypatch):
        from showup import fetch as fetch_module

        calls: list[str] = []
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(
            fetch_module.urllib.request,
            "urlopen",
            self._urlopen(
                [self._editions("20270217", "20260630"), json.dumps(_budget_rows()).encode()],
                calls,
            ),
        )
        rows = json.loads(fetch_module._fetch_board_budget_requests(lambda m: None))
        assert {row["publication"] for row in rows} == {"20260630"}
        assert "publication%3D%2720260630%27" in calls[1]
        limit = int(calls[1].split("%24limit=")[1].split("&")[0])
        assert limit > 3809, "Socrata pages at 1,000 by default; the limit must be explicit"


class TestDistrictScrapeRetry:
    """The whole set gets one retry pass before the fetch is refused.

    A cold run lost four of 51 pages to transient DNS failures, and a fresh clone has no
    previous cache to keep (docs/OBSERVATIONS.md, 2026-09-23).
    """

    @staticmethod
    def _urlopen_failing_once(fail_for: set[int]):
        """Fail the given district numbers on first request, succeed afterwards."""
        import io
        import urllib.error

        seen: dict[int, int] = {}

        class _Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        def fake(request, timeout=None):
            number = int(request.full_url.rstrip("/").rsplit("-", 1)[1])
            seen[number] = seen.get(number, 0) + 1
            if number in fail_for and seen[number] <= 3:
                raise urllib.error.URLError("nodename nor servname provided")
            return _Response(f"<h1>District {number}</h1>".encode())

        return fake, seen

    def test_a_transient_failure_is_rescued_by_the_retry_pass(self, monkeypatch):
        from showup import fetch as fetch_module

        fake, _seen = self._urlopen_failing_once({19, 20, 21, 22})
        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(fetch_module.urllib.request, "urlopen", fake)

        messages: list[str] = []
        pages = json.loads(fetch_module._fetch_district_pages(messages.append))

        assert all(pages[str(n)] for n in range(1, 52)), "the retry pass did not rescue them"
        assert any("retrying 4 page(s)" in m for m in messages)
        source = next(s for s in SOURCES if s.name == "districts")
        assert source.invariant(json.dumps(pages).encode()) is None

    def test_a_page_that_fails_twice_is_reported_and_left_null(self, monkeypatch):
        import urllib.error

        from showup import fetch as fetch_module

        def always_fail_seven(request, timeout=None):
            import io

            number = int(request.full_url.rstrip("/").rsplit("-", 1)[1])
            if number == 7:
                raise urllib.error.URLError("permanently gone")

            class _Response(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.close()
                    return False

            return _Response(f"<h1>District {number}</h1>".encode())

        monkeypatch.setattr(fetch_module.time, "sleep", lambda s: None)
        monkeypatch.setattr(fetch_module, "_polite_wait", lambda host: None)
        monkeypatch.setattr(fetch_module.urllib.request, "urlopen", always_fail_seven)

        messages: list[str] = []
        pages = json.loads(fetch_module._fetch_district_pages(messages.append))

        assert pages["7"] is None
        assert any("failed twice: [7]" in m for m in messages)
        source = next(s for s in SOURCES if s.name == "districts")
        assert "of 51 district pages" in source.invariant(json.dumps(pages).encode())
