"""The OMB register of community board budget requests, `vn4m-mk4t`.

Four upstream facts are each a silent bug if ignored, all recorded in
docs/OBSERVATIONS.md on 2026-09-30, and each has a test here that fails if the code
drifts back: the borough code is alphabetical rather than standard, the newest
publication is dated in the future, `priority` repeats within a board, and `response`
must never be bucketed.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from showup.sources.budget_requests import (
    BOARD_CODE_BY_BORO,
    BudgetRequestError,
    _category,
    load_budget_requests,
    select_publication,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REGISTER = FIXTURES / "board_budget_requests.json"
TODAY = date(2026, 9, 22)


@pytest.fixture(scope="module")
def register() -> dict:
    return load_budget_requests(REGISTER, today=TODAY)


def _row(**overrides: object) -> dict:
    row = {
        "publication": "20260630",
        "boro": "2",
        "board": "02",
        "priority": "01",
        "tracking_code": "202202701C",
        "request": "Reconstruct or upgrade a park",
        "explanation": "The board explains why.",
        "response": "OMB supports the agency's position as follows:",
        "responded_by": "OMB",
        "responsible_agency": "Department of Parks and Recreation",
    }
    row.update(overrides)
    return row


def _written(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "board_budget_requests.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


class TestTheBoroughCodeIsAlphabeticalNotStandard:
    """`boro` runs BX, BK, MN, QN, SI. Reading it as the standard NYC code swaps three
    boroughs, so every assertion here is pinned by a place name in the board's own words."""

    def test_the_mapping_is_the_one_the_data_shows(self):
        assert BOARD_CODE_BY_BORO == {"1": "2", "2": "3", "3": "1", "4": "4", "5": "5"}

    def test_boro_one_board_one_is_the_bronx(self, register):
        explanations = " ".join(r.explanation or "" for r in register["201"].requests)
        assert "Mott Haven" in explanations

    def test_boro_three_board_one_is_manhattan(self, register):
        explanations = " ".join(r.explanation or "" for r in register["101"].requests)
        assert "Lower manhattan" in explanations

    def test_boro_two_board_one_is_brooklyn(self, register):
        explanations = " ".join(r.explanation or "" for r in register["301"].requests)
        assert "Greenpoint" in explanations

    def test_boro_four_board_one_is_queens(self, register):
        explanations = " ".join(r.explanation or "" for r in register["401"].requests)
        assert "Hallets Cove" in explanations

    def test_boro_five_board_one_is_staten_island(self, register):
        explanations = " ".join(r.explanation or "" for r in register["501"].requests)
        assert "Bay Street" in explanations

    def test_a_boro_value_outside_the_five_is_dropped_not_guessed(self, tmp_path):
        path = _written(tmp_path, [_row(), _row(boro="9", tracking_code="902202701C")])
        assert set(load_budget_requests(path, today=TODAY)) == {"302"}

    def test_a_board_number_that_is_not_two_digits_is_dropped(self, tmp_path):
        path = _written(tmp_path, [_row(), _row(board="XX", tracking_code="20222701C")])
        assert set(load_budget_requests(path, today=TODAY)) == {"302"}


class TestTheNewestPublicationIsRefused:
    """`20270217` is dated five months ahead and is not a duplicate — same tracking
    codes as `20260630`, terser responses. `ORDER BY publication DESC LIMIT 1` serves it."""

    def test_the_fixture_really_carries_the_future_edition(self):
        rows = json.loads(REGISTER.read_text(encoding="utf-8"))
        assert "20270217" in {row["publication"] for row in rows}

    def test_the_selected_publication_is_the_newest_past_one(self, register):
        assert register["302"].publication == date(2026, 6, 30)

    def test_no_future_dated_row_survives_the_load(self, register):
        codes = {r.tracking_code for r in register["302"].requests}
        rows = json.loads(REGISTER.read_text(encoding="utf-8"))
        future = {row["tracking_code"] for row in rows if row["publication"] == "20270217"}
        assert future & codes, "the fixture should share tracking codes between editions"
        for request in register["302"].requests:
            assert request.response != "Agency does not support and cannot accommodate", (
                "a terser future-edition response reached the artifact"
            )

    def test_selection_prefers_the_newest_of_several_past_editions(self):
        chosen = select_publication(["20250630", "20260630", "20260512"], date(2026, 9, 22))
        assert chosen == date(2026, 6, 30)

    def test_a_register_with_only_future_editions_fails_closed(self):
        with pytest.raises(BudgetRequestError, match="on or before"):
            select_publication(["20270217"], date(2026, 9, 22))

    def test_an_unparseable_stamp_is_not_treated_as_a_date(self):
        with pytest.raises(BudgetRequestError, match="on or before"):
            select_publication(["not-a-date", "20261332", ""], date(2026, 9, 22))

    def test_a_future_only_register_on_disk_refuses_rather_than_rendering(self, tmp_path):
        path = _written(tmp_path, [_row(publication="20270217")])
        with pytest.raises(BudgetRequestError, match="on or before"):
            load_budget_requests(path, today=TODAY)

    def test_the_publication_is_pinned_so_the_page_can_cite_it(self, register):
        for entry in register.values():
            assert entry.publication == date(2026, 6, 30)


class TestAbsenceIsNotAFailure:
    def test_a_missing_register_loads_as_nothing(self, tmp_path):
        assert load_budget_requests(tmp_path / "nope.json", today=TODAY) == {}

    def test_an_empty_register_loads_as_nothing(self, tmp_path):
        assert load_budget_requests(_written(tmp_path, []), today=TODAY) == {}


class TestPriorityRepeatsSoThereIsNoTopRequest:
    """1,387 rows citywide carry priority 01 because priority ranks inside a budget
    category. Brooklyn CB2's fixture rows show five at priority 01."""

    def test_priority_repeats_within_one_board(self, register):
        priorities = [r.priority for r in register["302"].requests]
        assert priorities.count("01") > 1

    def test_requests_are_ordered_by_priority_then_register_reference(self, register):
        keys = [(r.priority, r.tracking_code) for r in register["302"].requests]
        assert keys == sorted(keys)

    def test_the_category_comes_from_the_tracking_code_suffix(self):
        assert _category("202202701C") == "Capital"
        assert _category("301202701CS") == "Capital support"
        assert _category("101202701E") == "Expense"

    def test_an_unrecognised_suffix_is_left_unlabelled(self):
        assert _category("202202701Z") is None
        assert _category("nonsense") is None

    def test_priority_is_kept_zero_padded_as_published(self, register):
        assert all(len(r.priority) == 2 for r in register["302"].requests)


class TestTheResponseIsQuotedNeverBucketed:
    """Its leading sentence looks classifiable but the phrasing varies between editions
    of the same row, so a bucket would turn a refusal into a promise."""

    def test_the_response_is_the_registers_own_wording(self, register):
        rows = json.loads(REGISTER.read_text(encoding="utf-8"))
        published = {
            row["tracking_code"]: " ".join(row["response"].split())
            for row in rows
            if row["publication"] == "20260630"
        }
        for request in register["302"].requests:
            assert request.response == published[request.tracking_code]

    def test_no_supported_or_refused_verdict_is_derived(self, register):
        request = register["302"].requests[0]
        assert not hasattr(request, "supported")
        assert not hasattr(request, "outcome")


class TestTheFiscalYear:
    def test_it_comes_from_the_tracking_codes(self, register):
        assert register["302"].fiscal_year == "2027"

    def test_a_publication_that_spans_years_reports_none(self, tmp_path):
        path = _written(tmp_path, [_row(), _row(tracking_code="202202601E", priority="02")])
        assert load_budget_requests(path, today=TODAY)["302"].fiscal_year is None

    def test_a_publication_with_no_usable_tracking_code_reports_none(self, tmp_path):
        path = _written(tmp_path, [_row(tracking_code="")])
        assert load_budget_requests(path, today=TODAY)["302"].fiscal_year is None


class TestHostileText:
    """Register text is upstream text, so §4.1 applies to every field of it."""

    HOSTILE = "<script>alert('x')</script>Fix the &amp; \"park\" <b>now</b>"

    def test_tags_are_stripped_from_every_text_field(self, tmp_path):
        path = _written(
            tmp_path,
            [
                _row(
                    request=self.HOSTILE,
                    explanation=self.HOSTILE,
                    response=self.HOSTILE,
                    responsible_agency=self.HOSTILE,
                )
            ],
        )
        request = load_budget_requests(path, today=TODAY)["302"].requests[0]
        for value in (request.request, request.explanation, request.response, request.agency):
            assert "<script>" not in value
            assert "<b>" not in value
            assert "alert" not in value
            assert value == 'Fix the & "park" now'

    def test_an_empty_field_becomes_none_rather_than_an_empty_string(self, tmp_path):
        path = _written(tmp_path, [_row(explanation="", response=None, responsible_agency="")])
        request = load_budget_requests(path, today=TODAY)["302"].requests[0]
        assert request.explanation is None
        assert request.response is None
        assert request.agency is None

    def test_a_request_with_no_description_is_none(self, tmp_path):
        path = _written(tmp_path, [_row(request="")])
        assert load_budget_requests(path, today=TODAY)["302"].requests[0].request is None


class TestCoverageAgainstTheRealRegister:
    def test_the_fixture_covers_every_borough(self, register):
        assert {code[0] for code in register} == {"1", "2", "3", "4", "5"}

    def test_every_code_is_a_real_board_code(self, register):
        boards = json.loads((FIXTURES / "community_boards.json").read_text(encoding="utf-8"))
        real = {row.get("community_board_1") for row in boards}
        assert set(register) <= real
