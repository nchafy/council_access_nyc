"""Venue normalisation over the real spelling variants.

Every raw string here was observed in the Legistar data. The variants are not
hypothetical: `meeting_location` is clerk-typed free text with 25 years of drift.
"""

from __future__ import annotations

import pytest

from showup.venues import normalize_location


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
