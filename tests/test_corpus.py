"""Run the committed corpus: input -> expected output, one test per case.

`tests/corpus/*.jsonl` is the project's durable record of what these functions do.
Each line carries an input, its expected output, and a note saying why the case
exists — because a case without a reason gets deleted by the next person who finds
it inconvenient.

The corpus is the artifact; `test_fuzz.py` is how it grows. When the fuzzer finds an
input that behaves interestingly, it goes in here with its expected result and gets
committed, which turns a one-off discovery into a permanent regression test.

Every case is its own parameterised test, so a failure names the input rather than
just the file.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from showup.deadlines import accommodation_deadline
from showup.sources.boards import _compose_address, email_policy
from showup.sources.calendar import parse_clock, parse_us_date
from showup.text import esc, strip_tags
from showup.urls import safe_url
from showup.venues import normalize_location

CORPUS = Path(__file__).parent / "corpus"


def load(name: str) -> list[dict[str, Any]]:
    path = CORPUS / f"{name}.jsonl"
    if not path.exists():  # pragma: no cover - a missing corpus file is a setup error
        raise FileNotFoundError(f"corpus file {path} is missing")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def cases(name: str):
    """Parameterise over a corpus file, using each case's note as its test id."""
    rows = load(name)
    return pytest.mark.parametrize(
        ("given", "expected"),
        [pytest.param(row["in"], row["out"], id=row["note"][:70]) for row in rows],
    )


# --------------------------------------------------------------------------- #
# The XSS boundary
# --------------------------------------------------------------------------- #


@cases("strip_tags")
def test_strip_tags(given, expected):
    assert strip_tags(given) == expected


@cases("esc")
def test_esc(given, expected):
    assert esc(given) == expected


@cases("safe_url")
def test_safe_url(given, expected):
    assert safe_url(given) == expected


# --------------------------------------------------------------------------- #
# Parsing upstream free text
# --------------------------------------------------------------------------- #


@cases("normalize_location")
def test_normalize_location(given, expected):
    venue, mode = normalize_location(given)
    assert [venue.id, mode] == expected


@cases("parse_clock")
def test_parse_clock(given, expected):
    result = parse_clock(given)
    assert (result.strftime("%H:%M") if result else None) == expected


@cases("parse_us_date")
def test_parse_us_date(given, expected):
    result = parse_us_date(given)
    assert (result.isoformat() if result else None) == expected


@cases("compose_address")
def test_compose_address(given, expected):
    assert _compose_address(given[0], given[1]) == expected


@cases("email_policy")
def test_email_policy(given, expected):
    assert list(email_policy(given)) == expected


@cases("accommodation_deadline")
def test_accommodation_deadline(given, expected):
    assert accommodation_deadline(date.fromisoformat(given)).isoformat() == expected


# --------------------------------------------------------------------------- #
# The corpus itself
# --------------------------------------------------------------------------- #

EXPECTED_FILES = {
    "strip_tags",
    "esc",
    "safe_url",
    "normalize_location",
    "parse_clock",
    "parse_us_date",
    "compose_address",
    "email_policy",
    "accommodation_deadline",
}


class TestCorpusHygiene:
    """The corpus is an artifact, so it gets its own invariants."""

    def test_every_expected_file_exists(self):
        present = {path.stem for path in CORPUS.glob("*.jsonl")}
        assert present >= EXPECTED_FILES, f"missing corpus files: {EXPECTED_FILES - present}"

    def test_no_orphan_corpus_files(self):
        """A corpus file nobody runs is a corpus file nobody maintains."""
        present = {path.stem for path in CORPUS.glob("*.jsonl")}
        assert present <= EXPECTED_FILES, f"corpus files with no runner: {present - EXPECTED_FILES}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
    def test_every_case_has_a_reason(self, name):
        for row in load(name):
            assert row.get("note"), f"{name}: a case with no note will be deleted by someone"
            assert "in" in row and "out" in row, f"{name}: malformed case {row}"

    @pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
    def test_no_duplicate_inputs(self, name):
        seen: set[str] = set()
        for row in load(name):
            key = json.dumps(row["in"], sort_keys=True)
            assert key not in seen, f"{name}: duplicate input {row['in']!r}"
            seen.add(key)

    @pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
    def test_notes_are_distinct_enough_to_identify_a_case(self, name):
        # Test ids come from notes; duplicates make a failure ambiguous.
        notes = [row["note"][:70] for row in load(name)]
        assert len(set(notes)) == len(notes), f"{name}: two cases share a test id"
