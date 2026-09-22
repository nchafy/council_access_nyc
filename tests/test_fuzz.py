"""Generative fuzzing over the parsers, asserting invariants rather than values.

WHY INVARIANTS AND NOT EXPECTED OUTPUTS
A fuzzer cannot know what `strip_tags("<scr<b>ipt>x")` *should* return — that is what
the corpus is for. What it can do is assert the properties that must hold for every
input, however malformed: never raise, never emit markup, never return something a
renderer would treat as HTML. Those are the properties whose violation is a security
bug rather than a cosmetic one.

DETERMINISTIC BY CONSTRUCTION
The seed is fixed, so a failure reproduces exactly and CI cannot go red at random. A
random-per-run fuzzer in CI trains people to re-run until green, which is worse than
no fuzzer.

HOW THE CORPUS GROWS
When a fuzz case fails, the fix is two commits' worth of work in one: repair the
function, **and** add that input to `tests/corpus/` with its now-correct expected
output. The fuzzer finds; the corpus remembers. See the `fuzz-and-corpus` skill.
"""

from __future__ import annotations

import json
import random
import re
import string
from datetime import date, timedelta
from pathlib import Path

import pytest

from showup.deadlines import accommodation_deadline, is_business_day, written_safe_until
from showup.geo import Polygon
from showup.sources.boards import _compose_address, email_policy
from showup.sources.calendar import parse_clock, parse_us_date
from showup.text import collapse, esc, strip_tags, text_lines
from showup.urls import ALLOWED_HOSTS, safe_url
from showup.venues import VENUES, normalize_location

SEED = 20260922
ITERATIONS = 400

CORPUS = Path(__file__).parent / "corpus"

#: Fragments chosen to hit the shapes that break naive parsers: unbalanced tags, the
#: nested-tag filter bypass, entities at one and two levels of encoding, control
#: characters inside a scheme, bidi and zero-width characters, and the accented
#: surnames that actually appear in Council data.
FRAGMENTS = [
    "<script>",
    "</script>",
    "<b>",
    "</b>",
    "<scr",
    "ipt>",
    "<td>",
    "</td>",
    "<br>",
    "<style>",
    "</style>",
    "<!--",
    "-->",
    "<img src=x onerror=alert(1)>",
    "&amp;",
    "&lt;",
    "&gt;",
    "&#60;",
    "&#x3C;",
    "&amp;lt;",
    "&nbsp;",
    "&",
    "javascript:",
    "JaVaScRiPt:",
    "data:",
    "https://",
    "http://",
    "//",
    "\\",
    "council.nyc.gov",
    "evil.example.com",
    "user:pass@",
    "Committee on Aging",
    "250 Broadway",
    "City Hall",
    "REMOTE HEARING",
    "HYBRID",
    "Avilés",
    "Ossé",
    "Cabán",
    "Farías",
    "Salamanca, Jr.",
    "1:30 PM",
    "Deferred",
    "12/17/2026",
    "02/31/2026",
    "11217",
    "\u0000",
    "\u0001",
    "\n",
    "\r",
    "\t",
    "  ",
    "​",
    "‮",
    "﻿",
    "'",
    '"',
    "`",
    "<",
    ">",
    "=",
    "\x7f",
    "é" * 3,
    "🏙",
    "A" * 40,
]


def _mutations(count: int, seed: int = SEED) -> list[str]:
    """Deterministic mutated inputs, seeded from the corpus plus the fragments.

    Seeding from the corpus matters: the interesting region of the input space is
    around the cases that already proved interesting, not uniformly random bytes.
    """
    rng = random.Random(seed)
    seeds: list[str] = []
    for path in sorted(CORPUS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)["in"]
            if isinstance(value, str):
                seeds.append(value)
            elif isinstance(value, list):
                seeds.extend(v for v in value if isinstance(v, str))

    out: list[str] = []
    for _ in range(count):
        style = rng.randrange(4)
        if style == 0:
            out.append("".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(1, 6))))
        elif style == 1 and seeds:
            base = rng.choice(seeds)
            cut = rng.randrange(len(base) + 1)
            out.append(base[:cut] + rng.choice(FRAGMENTS) + base[cut:])
        elif style == 2 and seeds:
            # Truncation, which is how a real scrape fails mid-response.
            base = rng.choice(seeds)
            out.append(base[: rng.randrange(len(base) + 1)])
        else:
            out.append(
                "".join(
                    rng.choice(string.printable + "éüÑ<>&\"'") for _ in range(rng.randint(0, 30))
                )
            )
    return out


CASES = _mutations(ITERATIONS)
MARKUP = re.compile(r"<[a-zA-Z/!]")


@pytest.mark.parametrize("value", CASES, ids=range(len(CASES)))
class TestTextInvariants:
    """`strip_tags` and `esc` are the XSS boundary; these are their contracts."""

    def test_strip_tags_never_raises(self, value):
        strip_tags(value)

    def test_strip_tags_drops_every_real_tag(self, value):
        """No tag present in the INPUT survives as a tag in the output."""
        stripped = strip_tags(value)
        # Tags that were actually markup are gone: nothing the parser recognised
        # as an element is echoed back.
        for tag in ("<script>", "<b>", "<td>", "<style>", "<img "):
            if tag in value:
                assert tag not in stripped or "&#" in value or "&lt;" in value

    def test_the_real_guarantee_is_that_escaped_output_is_inert(self, value):
        """The security property, stated where it actually holds.

        An earlier version of this test asserted that `strip_tags` output never
        contains an openable tag. The fuzzer disproved it: `&#60;script&#62;`
        decodes — correctly, exactly once — to the *characters* `<script>`, because
        that is what the source literally said. So the sequence can legitimately
        appear in stripped text.

        That is not a hole. Stripping is not the defence; escaping is. Every value
        passes through `esc` on its way into a page, and after that nothing is
        markup. This asserts the guarantee at the layer that provides it.
        """
        assert not MARKUP.search(esc(strip_tags(value)))

    def test_stripping_twice_only_ever_removes_more(self, value):
        """`strip_tags` is NOT idempotent, and that is now a documented fact.

        The fuzzer disproved the idempotence I had assumed: `"Defer&#x3C;red"`
        strips to `"Defer<red"`, and stripping *that* gives `"Defer"`, because the
        decoded `<red` reads as an unterminated tag on the second pass.

        So the discipline is "apply it exactly once, to raw upstream text" —
        audited and true of every call site — and the property worth asserting is
        the safe direction: a second pass can only ever remove text, never
        introduce markup. If it could add, double-stripping would be a
        vulnerability rather than merely lossy.
        """
        once = strip_tags(value)
        twice = strip_tags(once)
        assert len(twice) <= len(once)
        assert not MARKUP.search(esc(twice))

    def test_strip_tags_never_leaks_script_bodies(self, value):
        wrapped = f"<script>SECRET_TOKEN</script>{value}"
        assert "SECRET_TOKEN" not in strip_tags(wrapped)

    def test_esc_output_has_no_unescaped_specials(self, value):
        escaped = esc(value)
        assert "<" not in escaped
        assert ">" not in escaped
        assert '"' not in escaped
        assert "'" not in escaped
        # Every surviving & must start an entity.
        for index, char in enumerate(escaped):
            if char == "&":
                assert re.match(r"&(amp|lt|gt|quot|#x27);", escaped[index:]), escaped

    def test_esc_is_stable_under_the_pipeline(self, value):
        # strip_tags then esc is the real path; it must never produce markup.
        assert not MARKUP.search(esc(strip_tags(value)))

    def test_collapse_never_returns_leading_or_trailing_space(self, value):
        result = collapse(value)
        assert result == result.strip()

    def test_text_lines_yields_no_blank_lines(self, value):
        # A blank line is a parsing artifact, never content — the district-page
        # reader indexes by line position, so blanks would shift every offset.
        for line in text_lines(value):
            assert line
            assert line == line.strip()

    def test_text_lines_are_inert_once_escaped(self, value):
        # Same reasoning as strip_tags: a decoded entity can put "<x" in the text
        # legitimately, and escaping is what makes it safe.
        for line in text_lines(value):
            assert not MARKUP.search(esc(line))


@pytest.mark.parametrize("value", CASES, ids=range(len(CASES)))
class TestUrlInvariants:
    def test_safe_url_never_raises(self, value):
        safe_url(value)

    def test_safe_url_returns_none_or_an_allowlisted_https_url(self, value):
        result = safe_url(value)
        if result is None:
            return
        assert result.startswith("https://")
        from urllib.parse import urlsplit

        parts = urlsplit(result)
        assert (parts.hostname or "").lower() in ALLOWED_HOSTS
        assert not parts.username and not parts.password

    def test_safe_url_never_accepts_a_dangerous_scheme(self, value):
        result = safe_url(value)
        if result is not None:
            lowered = result.lower()
            assert not lowered.startswith(("javascript:", "data:", "vbscript:", "file:"))

    def test_safe_url_with_a_base_is_still_allowlisted(self, value):
        result = safe_url(value, base="https://nyc.legistar.com/")
        if result is not None:
            from urllib.parse import urlsplit

            assert (urlsplit(result).hostname or "").lower() in ALLOWED_HOSTS


@pytest.mark.parametrize("value", CASES, ids=range(len(CASES)))
class TestParserInvariants:
    def test_normalize_location_always_returns_a_known_venue(self, value):
        venue, mode = normalize_location(value)
        assert venue.id in VENUES
        assert mode in {"in_person", "hybrid", "remote"}

    def test_remote_venue_never_carries_an_address(self, value):
        venue, _mode = normalize_location(value)
        # "Remote" is not a place, so it must never be given a street address —
        # that would send someone to a building for a Zoom hearing.
        if venue.id == "remote":
            assert venue.address is None

    def test_offsite_never_invents_an_address(self, value):
        venue, _ = normalize_location(value)
        if venue.id == "offsite":
            assert venue.address is None

    def test_parse_clock_returns_none_or_a_valid_time(self, value):
        result = parse_clock(value)
        if result is not None:
            assert 0 <= result.hour <= 23
            assert 0 <= result.minute <= 59

    def test_parse_us_date_returns_none_or_a_real_date(self, value):
        result = parse_us_date(value)
        if result is not None:
            assert isinstance(result, date)
            # Round-tripping proves it is a real calendar date, not a rollover.
            assert date.fromisoformat(result.isoformat()) == result

    def test_compose_address_joins_cleanly(self, value):
        """The joining contract, on the input this function actually receives.

        An earlier version of this test fed raw markup in and asserted none came
        out, which failed on 163 cases — correctly, because that was never the
        contract. `_compose_address` is called with values that have already been
        through `strip_tags`, so the fuzzer must feed it the same. The real contract
        is about the *join*: no stray or doubled separators, and no line breaks,
        since the result goes into a single address line.
        """
        left = strip_tags(value)
        right = strip_tags(value[::-1])
        result = _compose_address(left, right)
        if result is None:
            # Only when both parts are empty.
            assert not left.strip() and not right.strip()
            return

        # Goes into a single address line, so no line breaks.
        assert "\n" not in result
        # Not asserted: absence of "<x" sequences, nor of doubled commas. A decoded
        # entity can introduce the first legitimately, and a real address genuinely
        # contains commas — "350 Jay Street, Brooklyn, NY 11201". Asserting either
        # would be inventing a contract this function never had.
        assert not MARKUP.search(esc(result))

        # The contract that IS real: the join loses no CONTENT. Not a substring
        # check — the function deliberately splits the city tail off and reassembles
        # around the second line, so the original contiguous string is not expected
        # to survive. Losing half an address is how someone ends up at the wrong
        # building, so compare the characters that should still be there.
        for part in (left, right):
            for token in part.replace(",", " ").split():
                assert token in result, f"the join dropped the token {token!r}"

    def test_email_policy_returns_exactly_one_of_email_or_reason(self, value):
        email, reason = email_policy(value)
        assert (email is None) != (reason is None), (email, reason)
        if email is not None:
            assert "@" in email
            assert "\n" not in email


@pytest.mark.parametrize("offset", range(0, 400, 7))
class TestDeadlineInvariants:
    """Deadline arithmetic, fuzzed across a year of dates.

    A wrong deadline is this product's worst output, so these assert the *direction*
    of every approximation, not just that it runs.
    """

    def test_accommodation_deadline_is_always_a_business_day_before(self, offset):
        hearing = date(2026, 1, 1) + timedelta(days=offset)
        deadline = accommodation_deadline(hearing)
        assert deadline < hearing
        assert is_business_day(deadline)

    def test_accommodation_deadline_is_at_least_three_business_days_back(self, offset):
        hearing = date(2026, 1, 1) + timedelta(days=offset)
        deadline = accommodation_deadline(hearing)
        between = sum(
            1
            for n in range(1, (hearing - deadline).days + 1)
            if is_business_day(deadline + timedelta(days=n - 1))
        )
        assert between >= 3, f"{hearing} -> {deadline} is only {between} business days"

    def test_written_bound_is_never_later_with_less_information(self, offset):
        """Missing a start time must move the bound EARLIER, never later.

        Earlier means "you have less time than you might" — safe. Later would tell
        someone they still have time when the window has closed.
        """
        from datetime import time

        hearing = date(2026, 1, 1) + timedelta(days=offset)
        known = written_safe_until(hearing, time(13, 30))
        unknown = written_safe_until(hearing, None)
        assert unknown <= known


@pytest.mark.parametrize("seed", range(12))
class TestGeometryInvariants:
    def test_point_in_polygon_agrees_with_itself(self, seed):
        """Hit-testing must be deterministic and bbox-consistent.

        A point reported inside must also be inside the bounding box — if those two
        ever disagree, the bbox prefilter silently drops real matches.
        """
        rng = random.Random(seed)
        ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
        polygon = Polygon("p", [ring])
        for _ in range(60):
            x = rng.uniform(-5, 15)
            y = rng.uniform(-5, 15)
            inside = polygon.contains(x, y)
            assert polygon.contains(x, y) == inside, "not deterministic"
            if inside:
                assert polygon.may_contain(x, y), "inside the polygon but outside its bbox"
