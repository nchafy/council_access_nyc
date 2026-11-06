"""The map route's dark steps, asserted rather than judged.

`xp.css` has no dark mode, so `/map/`'s is this project's own. The values are read out of
`assets/map.css` itself, which is what makes this a check and not a record: edit a colour
there without re-measuring and the pair that no longer clears its threshold fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contrast import (
    DARK_PAIRS,
    NON_TEXT_MINIMUM,
    TEXT_MINIMUM,
    luminance,
    ratio,
    report,
    tokens,
)

ASSETS = Path(__file__).resolve().parents[2] / "src" / "showup" / "assets"


@pytest.fixture(scope="module")
def map_css() -> str:
    return (ASSETS / "map.css").read_text(encoding="utf-8")


class TestTheFormula:
    """WCAG 2.1's own worked values, so a broken formula cannot pass the pairs below."""

    def test_black_on_white_is_the_maximum(self):
        assert ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)

    def test_a_colour_against_itself_is_one(self):
        assert ratio("#3a6ea5", "#3a6ea5") == pytest.approx(1.0, abs=0.001)

    def test_the_ratio_does_not_depend_on_which_argument_is_the_background(self):
        assert ratio("#123456", "#fedcba") == pytest.approx(ratio("#fedcba", "#123456"))

    def test_shorthand_hex_expands(self):
        assert luminance("#fff") == pytest.approx(luminance("#ffffff"))

    def test_a_value_that_is_not_a_colour_is_refused(self):
        with pytest.raises(ValueError, match="not a hex colour"):
            luminance("#ff")


class TestTheStylesheetIsWhatIsRead:
    """Harness honesty: the parser must fail loudly rather than measure the wrong block."""

    def test_the_dark_block_differs_from_the_light_one(self, map_css):
        assert tokens(map_css, dark=True) != tokens(map_css, dark=False)

    def test_asking_for_dark_steps_of_a_sheet_that_has_none_is_an_error(self):
        with pytest.raises(ValueError, match="no dark :root block"):
            tokens(":root { --ink: #000; }", dark=True)

    def test_a_sheet_with_no_root_block_is_an_error(self):
        with pytest.raises(ValueError, match="no :root block"):
            tokens("body { color: red; }", dark=False)

    def test_a_root_block_with_no_colours_is_an_error(self):
        with pytest.raises(ValueError, match="no hex colours"):
            tokens(":root { --taskbar-h: 30px; }", dark=False)

    def test_every_pair_names_a_token_the_dark_block_declares(self, map_css):
        dark = tokens(map_css, dark=True)
        missing = sorted(
            {name for pair in DARK_PAIRS for name in pair[:2]} - set(dark),
        )
        assert not missing, f"map.css's dark block no longer declares {missing}"


class TestTheDarkStepsClearTheirThresholds:
    @pytest.mark.parametrize(
        ("foreground", "background", "need", "why"),
        DARK_PAIRS,
        ids=[f"{pair[0]}-on-{pair[1]}" for pair in DARK_PAIRS],
    )
    def test_the_pair_passes(self, map_css, foreground, background, need, why):
        dark = tokens(map_css, dark=True)
        measured = ratio(dark[foreground], dark[background])
        assert measured >= need, (
            f"{foreground} on {background} is {measured:.2f}:1, under the {need}:1 "
            f"{'SC 1.4.3' if need == TEXT_MINIMUM else 'SC 1.4.11'} floor for {why}"
        )

    @pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
    def test_the_warning_fill_carries_its_own_text(self, map_css, dark):
        """`xp.css` has no state colours, so both steps of this one are ours."""
        values = tokens(map_css, dark=dark)
        measured = ratio(values["--warn-ink"], values["--warn-bg"])
        assert measured >= TEXT_MINIMUM


class TestTheThresholdsAreTheStandardOnes:
    def test_text_and_non_text_minima(self):
        assert (TEXT_MINIMUM, NON_TEXT_MINIMUM) == (4.5, 3.0)

    def test_the_report_runs_clean_against_the_shipped_stylesheets(self):
        """The operator tool and this file must agree on the verdict."""
        assert report() == 0
