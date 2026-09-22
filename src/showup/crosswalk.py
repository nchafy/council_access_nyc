"""The council-district → community-board crosswalk.

Generated rarely, committed, and read by every build. Two reasons it is a file
rather than a build step:

1. **Cost.** The geometry sweep takes ~35 seconds. Council and community district
   lines change roughly once a decade (council lines after each census, community
   districts almost never), so paying that per build would be absurd.
2. **Review.** A generated crosswalk that lands in git is a diff a human can read.
   If a boundary change moves a board between districts, that shows up as a
   reviewable change rather than silently altering what the site tells people.

Regenerate with `showup crosswalk` after replacing either geometry file, then read
the diff before committing it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .geo import GRID_SPACING_DEG, MIN_SHARE, load_features, overlap_shares
from .sources.boards import JOINT_INTEREST_AREAS

__all__ = [
    "CROSSWALK_PATH",
    "CrosswalkError",
    "generate",
    "load",
    "load_boards_to_districts",
    "load_zips",
]

CROSSWALK_PATH = Path("crosswalks/council_to_boards.json")


class CrosswalkError(RuntimeError):
    """The crosswalk is missing, malformed, or does not cover all 51 districts."""


def generate(
    council_geojson: Path, community_geojson: Path, zip_geojson: Path | None = None
) -> dict:
    """Compute the crosswalk. Slow by design; called by `showup crosswalk` only."""
    council = load_features(council_geojson, "coundist")
    if len(council) != 51:
        raise CrosswalkError(f"expected 51 council districts, found {len(council)}")

    boards = load_features(community_geojson, "boro_cd", exclude=set(JOINT_INTEREST_AREAS))
    if len(boards) != 59:
        raise CrosswalkError(f"expected 59 community districts, found {len(boards)}")

    shares = overlap_shares(council, boards)
    # And the reverse direction. The two are not transposes of each other: a share
    # is always "of the containing polygon's sampled area", so
    # districts[35][302] = 0.44 means 44% of council district 35 sits in Brooklyn
    # CB 2, while boards[302][35] answers the different question of how much of
    # CB 2 sits in district 35. The board view needs the second.
    reverse = overlap_shares(boards, council)

    # ZIP -> council districts, so a reader can type "11217" instead of a street
    # address and never touch the geocoder. The city publishes *modified* ZCTAs,
    # which merge some real ZIPs into one area, so each feature's `zcta` field is
    # expanded back out to the ZIPs a person would actually type.
    zips: dict[str, list[list]] = {}
    if zip_geojson and Path(zip_geojson).exists():
        zctas = load_features(zip_geojson, "modzcta")
        zcta_shares = overlap_shares(zctas, council, min_share=0.02)
        members = _zcta_members(zip_geojson)
        for code, pairs in zcta_shares.items():
            if not pairs:
                continue
            for real_zip in members.get(code, [code]):
                zips[real_zip] = [[district, share] for district, share in pairs]

    uncovered = sorted((key for key, value in shares.items() if not value), key=int)
    if uncovered:
        # Every council district must reach at least one board, or the page for
        # that district silently loses its most locally useful block. This is the
        # floor that caught the naive `council_district` join, which left seven
        # districts empty.
        raise CrosswalkError(f"council districts with no community board: {uncovered}")

    return {
        "generated_on": date.today().isoformat(),
        "method": (
            "lattice sampling at "
            f"{GRID_SPACING_DEG} degrees (~110 m), shares below {MIN_SHARE} dropped as slivers"
        ),
        "sources": {
            "council_districts": "NYC Open Data 872g-cjhh",
            "community_districts": "NYC Open Data 5crt-au7u (joint interest areas excluded)",
        },
        "note": (
            "Shares are approximate and are of sampled land area within the council "
            "district. They may sum to less than 1 where water or unsampled gaps fall "
            "inside the district. Ordering is stable; treat the numbers as indicative."
        ),
        "districts": {
            key: [[code, share] for code, share in value]
            for key, value in sorted(shares.items(), key=lambda kv: int(kv[0]))
        },
        "boards": {
            key: [[code, share] for code, share in value]
            for key, value in sorted(reverse.items(), key=lambda kv: int(kv[0]))
        },
        "zips": dict(sorted(zips.items())),
    }


def _zcta_members(path: Path) -> dict[str, list[str]]:
    """modzcta code -> the real ZIP codes it represents.

    `10001` is published as a modified ZCTA covering `10001, 10119, 10199`, and a
    resident types one of the members, not the modified code.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        code = str(props.get("modzcta", "")).strip()
        if not code:
            continue
        raw = str(props.get("zcta") or props.get("label") or code)
        members = [part.strip() for part in raw.split(",") if part.strip().isdigit()]
        out[code] = members or [code]
    return out


def load(path: Path) -> dict[int, list[tuple[str, float]]]:
    """Council district -> its community boards. Validates coverage of all 51."""
    file = Path(path)
    if not file.exists():
        raise CrosswalkError(
            f"{file} is missing. Run `showup crosswalk` to generate it, then commit it."
        )
    data = json.loads(file.read_text(encoding="utf-8"))
    districts = data.get("districts") or {}

    result: dict[int, list[tuple[str, float]]] = {}
    for key, pairs in districts.items():
        result[int(key)] = [(str(code), float(share)) for code, share in pairs]

    missing = [number for number in range(1, 52) if not result.get(number)]
    if missing:
        raise CrosswalkError(f"crosswalk covers no board for council districts {missing}")
    return result


def load_boards_to_districts(path: Path) -> dict[str, list[tuple[int, float]]]:
    """Community district code -> the council districts overlapping it.

    Shares here are of the *board's* area, which is the question the board view
    asks ("how much of this board is in council district 35"). That is a different
    number from the one on the district page, so the two directions are stored
    separately rather than transposed.
    """
    file = Path(path)
    if not file.exists():
        raise CrosswalkError(f"{file} is missing. Run `showup crosswalk`.")
    data = json.loads(file.read_text(encoding="utf-8"))
    boards = data.get("boards")
    if not boards:
        raise CrosswalkError(
            f"{file} has no `boards` section — regenerate it with `showup crosswalk`"
        )
    result = {
        str(code): [(int(district), float(share)) for district, share in pairs]
        for code, pairs in boards.items()
    }
    if len(result) != 59:
        raise CrosswalkError(f"crosswalk covers {len(result)} community boards, expected 59")
    empty = sorted(code for code, pairs in result.items() if not pairs)
    if empty:
        raise CrosswalkError(f"community boards with no council district: {empty}")
    return result


def load_zips(path: Path) -> dict[str, list[tuple[int, float]]]:
    """ZIP code -> the council districts it overlaps, largest share first.

    A ZIP is not a district and routinely straddles two or three, so this returns
    every overlap rather than a single answer. The UI offers the choice instead of
    guessing which one the reader meant.
    """
    file = Path(path)
    if not file.exists():
        raise CrosswalkError(f"{file} is missing. Run `showup crosswalk`.")
    data = json.loads(file.read_text(encoding="utf-8"))
    return {
        str(code): [(int(district), float(share)) for district, share in pairs]
        for code, pairs in (data.get("zips") or {}).items()
    }
