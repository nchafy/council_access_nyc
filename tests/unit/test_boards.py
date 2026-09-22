"""Community board loading and the email policy.

The email policy is a product decision with a privacy dimension, so the tests
state the decision explicitly rather than just locking in current behaviour. If
someone reverses the decision, these tests should fail loudly and be rewritten
deliberately.
"""

from __future__ import annotations

import json

import pytest

from showup.sources.boards import (
    JOINT_INTEREST_AREAS,
    _compose_address,
    email_policy,
    load_boards,
    looks_person_named,
)


@pytest.fixture
def boards_file(tmp_path):
    rows = [
        {
            "borough": "Brooklyn",
            "community_board": "Community Board 2",
            "community_board_1": "302",
            "neighborhoods": "Fort Greene, Brooklyn Heights",
            "cb_office_address": "350 Jay Street, 8th Floor",
            "cb_address_line_2": "Brooklyn, NY 11201",
            "cb_office_phone": "718-596-5410",
            "cb_office_email": "bk02@cb.nyc.gov",
            "cb_website": "https://www.nyc.gov/site/brooklyncb2/index.page",
            "cb_chair": "Some Chairperson",
            "cb_district_manager": "Some Manager",
            "cb_board_meeting": "Second Wednesday, 6:00pm",
            "cb_cabinet_meeting": "First Wednesday, 10:00am",
        },
        {
            "borough": "Manhattan",
            "community_board": "Community Board 9",
            "community_board_1": "109",
            "cb_office_email": "eprince@cb.nyc.gov",
            "cb_district_manager": "Eutha Prince",
            "cb_chair": "Victor Edwards",
            "cb_website": "http://insecure.example.com",
        },
        {
            "borough": "Bronx",
            "community_board": "Community Board 11",
            "community_board_1": "211",
            "cb_office_email": "",
        },
    ]
    path = tmp_path / "boards.json"
    path.write_text(json.dumps(rows))
    return path


class TestEmailPolicy:
    def test_publishes_an_institutional_address(self):
        assert email_policy("bk02@cb.nyc.gov") == ("bk02@cb.nyc.gov", None)

    def test_publishes_a_board_domain_address(self):
        # R30's strict cb.nyc.gov regex would have withheld this; it is the
        # board's own institutional mailbox.
        assert email_policy("info@brooklyncb6.org")[0] == "info@brooklyncb6.org"

    def test_publishes_a_consumer_mailbox(self):
        # Unprofessional, but it is the contact the board actually published and a
        # resident needs a working route.
        assert email_policy("brooklyncb8@gmail.com")[0] == "brooklyncb8@gmail.com"

    def test_publishes_a_district_manager_work_address(self):
        """The decision: a public employee's published work email is published.

        11 boards publish only this shape, all on cb.nyc.gov. Withholding them
        removes the sole contact route for a fifth of the city's boards to hide an
        address the City itself publishes for exactly this purpose. The harm worth
        avoiding is pairing a name to a mailbox, and we never render the names.
        """
        assert email_policy("eprince@cb.nyc.gov")[0] == "eprince@cb.nyc.gov"

    def test_missing_email_reports_a_reason(self):
        email, reason = email_policy("")
        assert email is None
        assert reason == "no email published"

    def test_malformed_email_reports_a_reason(self):
        email, reason = email_policy("not-an-address")
        assert email is None
        assert "not a usable address" in reason


class TestLooksPersonNamed:
    """Kept and tested although the policy no longer uses it — it is the
    mechanism a future reversal would need, and the count it produces is the
    evidence the decision rests on."""

    def test_detects_initial_plus_surname(self):
        assert looks_person_named("eprince@cb.nyc.gov", "Victor Edwards", "Eutha Prince")

    def test_detects_full_surname(self):
        assert looks_person_named("kcabreracarrera@cb.nyc.gov", None, "Karla Cabrera Carrera")

    def test_role_mailbox_is_not_person_named(self):
        assert not looks_person_named("info@brooklyncb6.org", "Jane Doe", "John Smith")

    def test_short_tokens_are_ignored(self):
        # Matching 3-letter names would suppress "college@", "info@" and friends.
        assert not looks_person_named("info@cb.nyc.gov", "Amy Ng", "Bob Lee")


class TestLoadBoards:
    def test_keys_on_the_borough_prefixed_code(self, boards_file):
        boards = load_boards(boards_file)
        assert set(boards) == {"302", "109", "211"}

    def test_label_disambiguates_boroughs(self, boards_file):
        # Four boroughs each have a "Community Board 9", so the label must carry
        # the borough or the page is ambiguous.
        assert load_boards(boards_file)["109"].label == "Manhattan Community Board 9"
        assert load_boards(boards_file)["302"].label == "Brooklyn Community Board 2"

    def test_address_lines_are_joined(self, boards_file):
        board = load_boards(boards_file)["302"]
        assert board.address == "350 Jay Street, 8th Floor, Brooklyn, NY 11201"

    def test_meeting_cadence_is_verbatim(self, boards_file):
        # Never parsed into a date: boards move meetings without updating this.
        assert load_boards(boards_file)["302"].board_meeting == "Second Wednesday, 6:00pm"

    def test_http_website_is_rejected(self, boards_file):
        assert load_boards(boards_file)["109"].website is None

    def test_https_website_on_any_host_is_allowed(self, boards_file):
        # Board sites live on their own domains, so the project allowlist cannot
        # cover them; https-only is the guard.
        assert load_boards(boards_file)["302"].website.startswith("https://")

    def test_missing_email_records_the_reason(self, boards_file):
        board = load_boards(boards_file)["211"]
        assert board.email is None
        assert board.email_suppressed == "no email published"


def test_joint_interest_areas_are_the_twelve_non_boards():
    # 71 geometry features minus these 12 is exactly the 59 real boards.
    assert len(JOINT_INTEREST_AREAS) == 12
    assert "164" in JOINT_INTEREST_AREAS  # Central Park


class TestComposeAddress:
    """`cb_office_address` runs street and city together with no separator, and
    the floor lives in a second field, so a naive join strands it after the ZIP.
    16 of 59 boards have a second line."""

    def test_line_two_lands_before_the_city(self):
        assert (
            _compose_address("350 Jay Street Brooklyn, NY 11201", "8th Floor")
            == "350 Jay Street, 8th Floor, Brooklyn, NY 11201"
        )

    def test_handles_spaced_state_abbreviation(self):
        assert (
            _compose_address("1243 Woodrow Road Staten Island, N. Y. 10309", "2nd Floor")
            == "1243 Woodrow Road, 2nd Floor, Staten Island, N. Y. 10309"
        )

    def test_handles_a_missing_zip(self):
        assert (
            _compose_address("211 East 43rd Street, New York, NY", "Suite 1404")
            == "211 East 43rd Street, Suite 1404, New York, NY"
        )

    def test_no_city_tail_falls_back_to_appending(self):
        # Readable and correct, just not postal order — better than a regex tuned
        # until it starts guessing.
        assert (
            _compose_address("30-50 Whitestone Expressway Flushing/Whitestone", "Suite 205")
            == "30-50 Whitestone Expressway Flushing/Whitestone, Suite 205"
        )

    def test_only_one_field_present(self):
        assert _compose_address("1 Main St", "") == "1 Main St"
        assert _compose_address("", "Suite 5") == "Suite 5"
        assert _compose_address("", "") is None
