"""The two participatory-budgeting rosters, and the refusals that keep them honest.

The upstream facts these pin, all recorded in docs/OBSERVATIONS.md on 2026-10-27:

- a results release states its own district count, which is the only check on the parse;
- the idea map states no year, no fiscal year and no vote date, so no cycle label may be
  derived from it;
- the two rosters disagree — 24 open, 22 in FY2027, 21 in both — so participation is a
  fact about a cycle and never a standing property of a district.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from showup import fetch as fetch_module
from showup.sources.participatory_budgeting import (
    IDEA_MAP_URL,
    PB_DISTRICT_FLOOR,
    Participation,
    ParticipatoryBudgetingError,
    districts_in_release,
    is_results_release,
    load_participation,
    parse_idea_map,
    parse_results_release,
    participation_from_payload,
    stated_district_count,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "participatory_budgeting.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def participation(payload: dict) -> Participation:
    return participation_from_payload(payload)


def _post(*, title: str, body: str, when: str = "2026-05-22T12:29:47") -> dict:
    return {
        "date": when,
        "title": {"rendered": title},
        "content": {"rendered": body},
    }


def _release_body(districts: list[int], *, stated: int | None = None) -> str:
    stated = len(districts) if stated is None else stated
    rows = " ".join(
        f"<p><strong>District {n} &#8211; Council Member X</strong></p>" for n in districts
    )
    return f"<p>across {stated} Council Districts</p>{rows}"


TITLE = "Speaker Announces Results of FY 2027 Participatory Budgeting"


class TestTheRealRelease:
    """The byte-exact release the Council published on 2026-05-22."""

    def test_both_rosters_load(self, participation: Participation):
        assert len(participation.open_cycle) == 24
        assert participation.results is not None
        assert len(participation.results.districts) == 22

    def test_the_cycle_label_comes_from_the_title(self, participation: Participation):
        assert participation.results.cycle == "FY 2027"

    def test_the_publication_date_comes_from_the_post(self, participation: Participation):
        assert participation.results.published == date(2026, 5, 22)

    def test_the_release_states_the_count_it_is_checked_against(self, payload: dict):
        body = payload["release"]["content"]["rendered"]
        assert stated_district_count(body) == len(districts_in_release(body)) == 22

    def test_the_two_rosters_disagree(self, participation: Participation):
        """The whole reason participation is reported per cycle rather than once."""
        open_cycle = set(participation.open_cycle)
        past = set(participation.results.districts)
        assert open_cycle != past
        assert len(open_cycle & past) == 21
        assert open_cycle - past == {4, 17, 21}
        assert past - open_cycle == {8}

    def test_every_number_is_a_real_district(self, participation: Participation):
        for number in (*participation.open_cycle, *participation.results.districts):
            assert 1 <= number <= 51


class TestTheIdeaMap:
    def test_the_member_table_is_not_evidence_of_participation(self, participation):
        """Every district's member is listed in a table on that page. A name there says
        nothing about whether the district is running a cycle."""
        assert 50 not in participation.open_cycle

    def test_script_and_style_numbers_are_not_districts(self, participation):
        assert not {99, 52, 0} & set(participation.open_cycle)

    def test_a_roster_below_the_floor_is_refused(self):
        markup = "".join(f'<div data-district="{n}"></div>' for n in range(1, 5))
        with pytest.raises(ParticipatoryBudgetingError, match="floor"):
            parse_idea_map(markup)

    def test_the_refusal_names_the_page(self):
        with pytest.raises(ParticipatoryBudgetingError, match=IDEA_MAP_URL):
            parse_idea_map("<html></html>")

    def test_duplicates_count_once(self):
        markup = "".join(f'<div data-district="{n}"></div>' for n in range(1, 20)) * 3
        assert len(parse_idea_map(markup)) == 19


class TestTheChecksumRefusals:
    """A release that does not agree with itself must stop the build. A district silently
    dropped from the roster renders as "not taking part", which is a wrong answer."""

    def test_a_parse_short_of_the_stated_count_is_refused(self):
        body = _release_body(list(range(1, 22)), stated=22)
        with pytest.raises(ParticipatoryBudgetingError, match="states 22 districts, parsed 21"):
            parse_results_release(_post(title=TITLE, body=body), url="u")

    def test_a_parse_over_the_stated_count_is_refused(self):
        body = _release_body(list(range(1, 24)), stated=22)
        with pytest.raises(ParticipatoryBudgetingError, match="states 22 districts, parsed 23"):
            parse_results_release(_post(title=TITLE, body=body), url="u")

    def test_a_release_stating_no_count_is_refused(self):
        rows = " ".join(f"<p>District {n}</p>" for n in range(1, 23))
        with pytest.raises(ParticipatoryBudgetingError, match="states no district count"):
            parse_results_release(_post(title=TITLE, body=rows), url="u")

    def test_an_agreeing_release_below_the_floor_is_refused(self):
        body = _release_body(list(range(1, 5)))
        with pytest.raises(ParticipatoryBudgetingError, match=f"floor is {PB_DISTRICT_FLOOR}"):
            parse_results_release(_post(title=TITLE, body=body), url="u")

    def test_the_refusal_names_the_url_and_the_districts(self):
        body = _release_body(list(range(1, 22)), stated=22)
        with pytest.raises(ParticipatoryBudgetingError) as raised:
            parse_results_release(_post(title=TITLE, body=body), url="https://example.gov/x")
        assert "https://example.gov/x" in str(raised.value)
        assert "Refusing a partial roster" in str(raised.value)


class TestTheTitleGate:
    @pytest.mark.parametrize(
        "title",
        [
            "Speaker Announces Results of FY 2027 Participatory Budgeting",
            "results of fy2026 participatory budgeting",
            "Council Members Announce Results of FY  2024 Participatory Budgeting Cycle",
        ],
    )
    def test_a_results_release_is_recognised(self, title: str):
        assert is_results_release(title)

    @pytest.mark.parametrize(
        "title",
        [
            "Participatory Budgeting Vote Week Begins",
            "Speaker Announces Participatory Budgeting Cycle",
            "Results of FY 2027 Budgeting",
            "",
        ],
    )
    def test_anything_else_is_not(self, title: str):
        assert not is_results_release(title)

    def test_a_non_release_post_is_refused(self):
        post = _post(title="Vote Week Begins", body=_release_body(list(range(1, 23))))
        with pytest.raises(ParticipatoryBudgetingError, match="not a participatory budgeting"):
            parse_results_release(post, url="u")

    def test_an_unreadable_date_is_refused(self):
        post = _post(title=TITLE, body=_release_body(list(range(1, 23))), when="not-a-date")
        with pytest.raises(ParticipatoryBudgetingError, match="unreadable date"):
            parse_results_release(post, url="u")


class TestLoading:
    def test_a_missing_file_is_refused(self, tmp_path: Path):
        with pytest.raises(ParticipatoryBudgetingError, match="No such file"):
            load_participation(tmp_path / "absent.json")

    def test_unparseable_json_is_refused(self, tmp_path: Path):
        path = tmp_path / "pb.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ParticipatoryBudgetingError):
            load_participation(path)

    def test_a_json_array_is_refused(self, tmp_path: Path):
        path = tmp_path / "pb.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(ParticipatoryBudgetingError, match="expected a JSON object"):
            load_participation(path)

    def test_the_fixture_loads_from_disk(self):
        assert len(load_participation(FIXTURE).open_cycle) == 24

    def test_a_payload_without_a_release_keeps_the_open_roster(self, payload: dict):
        """The idea map alone is still an answer; the results row simply does not render."""
        trimmed = {**payload, "release": None}
        participation = participation_from_payload(trimmed)
        assert participation.results is None
        assert len(participation.open_cycle) == 24

    def test_the_idea_map_url_falls_back_to_the_constant(self, payload: dict):
        trimmed = {k: v for k, v in payload.items() if k != "idea_map_url"}
        assert participation_from_payload(trimmed).open_cycle_url == IDEA_MAP_URL


class TestTheFetcher:
    """`_fetch_participatory_budgeting` with `_get` substituted: it has to pick the right
    post out of the index, and refuse an index with no results release in it."""

    @staticmethod
    def _responses(payload: dict) -> dict[str, bytes]:
        return {
            f"{fetch_module.PRESS_API}?search=participatory+budgeting&per_page=100"
            "&_fields=id%2Cdate%2Clink%2Ctitle": json.dumps(
                [
                    {
                        "id": 1,
                        "date": "2024-04-05",
                        "link": "u1",
                        "title": {"rendered": "Vote Week"},
                    },
                    {
                        "id": 2892,
                        "date": "2025-05-30",
                        "link": "https://example.gov/2892",
                        "title": {"rendered": "Results of FY 2026 Participatory Budgeting"},
                    },
                    {
                        "id": 3126,
                        "date": "2026-05-22",
                        "link": "https://example.gov/3126",
                        "title": {"rendered": "Results of FY 2027 Participatory Budgeting"},
                    },
                ]
            ).encode(),
            f"{fetch_module.PRESS_API}/3126?_fields=id,date,title,content": json.dumps(
                payload["release"]
            ).encode(),
            IDEA_MAP_URL: payload["idea_map_html"].encode(),
        }

    def _patch(self, monkeypatch, responses: dict[str, bytes]) -> list[str]:
        asked: list[str] = []

        def fake_get(url: str, **_kwargs) -> bytes:
            asked.append(url)
            if url not in responses:  # pragma: no cover - a test wiring error
                raise AssertionError(f"unexpected URL {url}")
            return responses[url]

        monkeypatch.setattr(fetch_module, "_get", fake_get)
        return asked

    def test_it_takes_the_newest_results_release(self, monkeypatch, payload):
        asked = self._patch(monkeypatch, self._responses(payload))
        body = fetch_module._fetch_participatory_budgeting(lambda _message: None)

        assert any("/3126?" in url for url in asked), "did not fetch the newest release"
        assert not any("/2892?" in url for url in asked), "fetched a superseded release"
        cached = json.loads(body)
        assert cached["release_url"] == "https://example.gov/3126"
        assert fetch_module._participatory_budgeting(body) is None

    def test_an_index_with_no_release_is_refused(self, monkeypatch, payload):
        responses = self._responses(payload)
        index_url = next(url for url in responses if "?search=" in url)
        responses[index_url] = json.dumps(
            [{"id": 1, "date": "2024-04-05", "link": "u", "title": {"rendered": "Vote Week"}}]
        ).encode()
        self._patch(monkeypatch, responses)
        with pytest.raises(
            fetch_module.FetchError, match="is a participatory budgeting results release"
        ):
            fetch_module._fetch_participatory_budgeting(lambda _message: None)

    def test_a_non_array_index_is_refused(self, monkeypatch, payload):
        responses = self._responses(payload)
        index_url = next(url for url in responses if "?search=" in url)
        responses[index_url] = b'{"code":"rest_no_route"}'
        self._patch(monkeypatch, responses)
        with pytest.raises(fetch_module.FetchError, match="expected a JSON array"):
            fetch_module._fetch_participatory_budgeting(lambda _message: None)


class TestTheFetchInvariant:
    """What `fetch_one` checks before a download may replace a good cache entry."""

    def test_the_real_payload_passes(self, payload):
        assert fetch_module._participatory_budgeting(json.dumps(payload).encode()) is None

    def test_unparseable_json_is_refused(self):
        assert "not valid JSON" in fetch_module._participatory_budgeting(b"{oh no")

    def test_a_json_array_is_refused(self):
        assert "expected a JSON object" in fetch_module._participatory_budgeting(b"[]")

    def test_a_short_idea_map_is_refused(self, payload):
        broken = {**payload, "idea_map_html": '<div data-district="1"></div>'}
        assert "floor" in fetch_module._participatory_budgeting(json.dumps(broken).encode())

    def test_a_payload_with_no_release_is_refused(self, payload):
        """The open roster alone is a usable answer for the build, but a fetch that lost
        the release must not overwrite the copy that still has one."""
        trimmed = {**payload, "release": None}
        problem = fetch_module._participatory_budgeting(json.dumps(trimmed).encode())
        assert problem == "no results release in the payload"

    def test_a_release_failing_its_own_checksum_is_refused(self, payload):
        release = json.loads(json.dumps(payload["release"]))
        release["content"]["rendered"] = release["content"]["rendered"].replace(
            "22 Council Districts", "40 Council Districts"
        )
        broken = {**payload, "release": release}
        problem = fetch_module._participatory_budgeting(json.dumps(broken).encode())
        assert "states 40 districts, parsed 22" in problem
