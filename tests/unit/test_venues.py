"""Venue normalisation over the real spelling variants.

Every raw string here was observed in the Legistar data. The variants are not
hypothetical: `meeting_location` is clerk-typed free text with 25 years of drift.
"""

from __future__ import annotations

import re

import pytest

from showup.venues import VENUES, normalize_location


class TestCityHall:
    @pytest.mark.parametrize(
        "raw",
        [
            "Council Chambers - City Hall",
            "Council Chambers – City Hall",  # en dash
            "Council Chambers  - City Hall",  # double space
            "Council Chambers ~ City Hall",
        ],
    )
    def test_chambers_variants_collapse(self, raw):
        venue, mode = normalize_location(raw)
        assert venue.id == "city-hall-chambers"
        assert mode == "in_person"
        assert "City Hall Park" in venue.address

    def test_committee_room_is_not_chambers(self):
        venue, _ = normalize_location("Committee Room - City Hall")
        assert venue.id == "city-hall-committee"

    def test_council_committee_room_prefers_committee(self):
        # "Council Committee Room - City Hall" contains neither word exclusively;
        # committee has to win or it is filed as the Chambers.
        venue, _ = normalize_location("Council Committee Room - City Hall")
        assert venue.id == "city-hall-committee"


class TestBroadway:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("250 Broadway - 8th Floor - Hearing Room 1", "250-broadway-8"),
            ("250 Broadway - Committee Rm, 16th Fl.", "250-broadway-16"),
            ("250 Broadway - Hearing Room, 14th Fl.", "250-broadway-14"),
            ("250 Broadway, Hearing Room - 14th Fl.", "250-broadway-14"),
            ("Hearing Room, 250 Broadway, 16th Fl.", "250-broadway-16"),
        ],
    )
    def test_floor_is_extracted(self, raw, expected):
        venue, _ = normalize_location(raw)
        assert venue.id == expected

    def test_unknown_floor_falls_back_without_inventing_one(self):
        venue, _ = normalize_location("250 Broadway")
        assert venue.id == "250-broadway"
        assert "Floor not stated" in venue.note


class TestAttendanceMode:
    def test_remote_is_a_mode_not_a_room(self):
        venue, mode = normalize_location("REMOTE HEARING (VIRTUAL ROOM 3)")
        assert mode == "remote"
        assert venue.id == "remote"
        assert venue.address is None

    def test_hybrid_keeps_its_physical_room(self):
        # A hybrid hearing has a real address; treating it as remote would tell
        # someone there is nowhere to go.
        venue, mode = normalize_location("HYBRID HEARING - Council Chambers - City Hall")
        assert mode == "hybrid"
        assert venue.id == "city-hall-chambers"
        assert venue.address is not None

    def test_bare_remote(self):
        _, mode = normalize_location("- REMOTE HEARING -")
        assert mode == "remote"


class TestJointHearings:
    def test_jointly_clause_is_stripped_before_matching(self):
        # This clause rides along in the location cell. Left in, every joint
        # hearing looks like an unknown venue.
        venue, _ = normalize_location(
            "Council Chambers - City Hall Jointly with the Committee on Education."
        )
        assert venue.id == "city-hall-chambers"


class TestOffsite:
    def test_unknown_venue_is_offsite_not_guessed(self):
        venue, _ = normalize_location("Marine Park Intermediate School 278, 1925 Stuart Street")
        assert venue.id == "offsite"
        # Inventing a City Hall address here would send someone to Manhattan
        # instead of Brooklyn.
        assert venue.address is None

    def test_emigrant_building(self):
        venue, _ = normalize_location("Emigrant Savings Bank - 49-51 Chambers Street")
        assert venue.id == "emigrant"
        assert "49-51 Chambers" in venue.address

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_empty_is_offsite(self, raw):
        venue, mode = normalize_location(raw)
        assert venue.id == "offsite"
        assert mode == "in_person"


class TestVenueCopyStatesRatherThanInstructs:
    """docs/voice.md, applied to the one place it had not reached.

    These strings render inside every meeting card, five times per district page, and
    were the last second-person and imperative copy in the shipped pages. Every
    procedural fact is kept; only the mood changed, so this guards the mood.
    """

    SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|you're)\b", re.IGNORECASE)

    #: First words that address the reader. Hand-enumerated from the strings that were
    #: rewritten, so a reintroduced one fails here rather than in a copy review.
    IMPERATIVE_OPENERS = (
        "bring ",
        "check ",
        "enter ",
        "tell ",
        "use ",
        "register ",
        "pass ",
        "contact ",
        "visit ",
        "arrive ",
        "to speak,",
        "to watch",
    )

    @pytest.mark.parametrize("venue_id", sorted(VENUES))
    def test_no_second_person(self, venue_id):
        venue = VENUES[venue_id]
        for field in (venue.entry, venue.note):
            assert field is None or not self.SECOND_PERSON.search(field), field

    @pytest.mark.parametrize("venue_id", sorted(VENUES))
    def test_no_sentence_opens_with_an_instruction(self, venue_id):
        venue = VENUES[venue_id]
        for field in (venue.entry, venue.note):
            for sentence in (field or "").split(". "):
                opener = sentence.strip().lower()
                assert not opener.startswith(self.IMPERATIVE_OPENERS), sentence

    def test_the_facts_survived_the_rewrite(self):
        """The rewrite is a voice change, not a content cut, so the facts are pinned."""
        city_hall = VENUES["city-hall-chambers"].entry
        assert "NYPD security and metal detectors" in city_hall
        assert "which hearing" in city_hall
        assert '8.5" x 11"' in city_hall

        broadway = VENUES["250-broadway-8"].entry
        assert "Photo ID is required" in broadway
        assert "Sergeant-at-Arms" in broadway

        assert "Photo ID is required" in VENUES["emigrant"].entry

        remote = VENUES["remote"].entry
        assert "Register to Testify" in remote
        assert "advance registration" in remote
        assert "no registration" in remote
        assert "livestream" in remote

        assert "agenda PDF" in VENUES["offsite"].entry
