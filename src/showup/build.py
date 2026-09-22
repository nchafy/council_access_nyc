"""Assemble the static site.

Reads cached upstream payloads, produces `site/`. Nothing here talks to the
network: fetching is a separate stage (`etl/raw/` today, `showup fetch` next), so
the build is reproducible and testable offline, and a network failure can never
half-write a site.

Failure posture is **fail closed** (outline §2.13). A source that parses to fewer
rows than its floor raises, the build stops, and whatever was previously in
`site/` is left untouched — a stale site that says how old it is beats a fresh
site that is missing half its meetings.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

from .crosswalk import CROSSWALK_PATH, CrosswalkError, load_boards_to_districts, load_zips
from .crosswalk import load as load_crosswalk
from .geo import load_features, to_geojson
from .model import District, DistrictBoard, Manifest, Member
from .render import render_board, render_district, render_index, render_not_found
from .sources.boards import load_boards
from .sources.calendar import parse_calendar, upcoming
from .sources.districts import parse_district_page
from .sources.members import current_by_district, load_members

__all__ = ["SHORTLIST_SIZE", "BuildError", "build_site"]

#: Owner's decision: five items. In Phase 1 the shortlist is purely
#: chronological — the next five meetings — so it needs no ranking at all.
SHORTLIST_SIZE = 5

DISTRICT_COUNT = 51

#: Below these, the parse is treated as broken rather than as "not much data".
#: A floor is the difference between noticing a silent upstream change and
#: publishing an empty site with a confident tone.
FLOORS = {"calendar": 40, "district_pages": DISTRICT_COUNT, "members": 300, "boards": 59}


class BuildError(RuntimeError):
    """A source failed its floor or invariant. The build must not continue."""


def _check_floor(name: str, count: int) -> None:
    floor = FLOORS[name]
    if count < floor:
        raise BuildError(
            f"{name}: parsed {count} rows, floor is {floor}. "
            "Refusing to build — the upstream shape has probably changed. "
            "Leaving the previous site in place."
        )


def _load_boards_by_district(
    raw: Path, repo_root: Path
) -> tuple[dict[int, tuple[DistrictBoard, ...]], dict[str, DistrictBoard]]:
    """Join the committed geometry crosswalk to the boards' contact details.

    The crosswalk decides *which* boards cover a district (geometry); this dataset
    supplies *how to reach* them. Neither alone is enough: `ruf7-3wgc` also carries
    a `council_district` column, and using it would leave seven districts with no
    board at all.
    """
    boards = load_boards(raw / "community_boards.json")
    _check_floor("boards", len(boards))

    try:
        crosswalk = load_crosswalk(repo_root / CROSSWALK_PATH)
    except CrosswalkError as error:
        raise BuildError(str(error)) from error

    by_district: dict[int, tuple[DistrictBoard, ...]] = {}
    by_code: dict[str, DistrictBoard] = {}
    for number, pairs in crosswalk.items():
        entries = []
        for code, share in pairs:
            board = boards.get(code)
            if board is None:
                raise BuildError(
                    f"crosswalk references community district {code}, which is not in "
                    "community_boards.json — the two sources have drifted apart"
                )
            entry = DistrictBoard(
                code=code,
                label=board.label,
                borough_name=board.borough,
                share=share,
                neighborhoods=board.neighborhoods,
                address=board.address,
                phone=board.phone,
                email=board.email,
                email_suppressed=board.email_suppressed,
                website=board.website,
                board_meeting=board.board_meeting,
                cabinet_meeting=board.cabinet_meeting,
            )
            entries.append(entry)
            by_code.setdefault(code, entry)
        by_district[number] = tuple(entries)
    return by_district, by_code


def _load_districts(
    raw: Path, today: date
) -> tuple[list[District], dict[int, dict], dict[str, DistrictBoard]]:
    pages = json.loads((raw / "district_pages.json").read_text(encoding="utf-8"))
    members = load_members(raw / "members.json")
    _check_floor("members", len(members))
    current = current_by_district(members, today)

    parsed_pages = {}
    for number in range(1, DISTRICT_COUNT + 1):
        html_text = pages.get(str(number)) or pages.get(number)
        parsed_pages[number] = parse_district_page(number, html_text)
    _check_floor(
        "district_pages", sum(1 for p in parsed_pages.values() if "page" not in p["missing"])
    )

    boards_by_district, boards_by_code = _load_boards_by_district(
        raw, Path(__file__).resolve().parents[2]
    )

    seen_at = datetime.now().isoformat(timespec="seconds")
    districts: list[District] = []
    for number in range(1, DISTRICT_COUNT + 1):
        page = parsed_pages[number]
        seat = current.get(number)

        # The two sources can genuinely disagree, and District 3 shows how:
        # `uvw5-9znb` records Erik Bottcher's term ending 2026-02-03 with no
        # successor row, while council.nyc.gov already names Carl Wilson. The
        # scraped page is the fresher of the two — a special election lands there
        # weeks before it lands in the open dataset.
        #
        # So a seat counts as filled when *either* source says someone holds it.
        # Getting this backwards would tell a district with a sitting member that
        # it has no representation, which is worse than a slightly stale name.
        name = page["member_name"] or (seat["name"] if seat else None)
        seat_conflict = bool(name) and seat is None
        member = (
            Member(
                name=name or "Name not published",
                seat_status="filled" if (seat or name) else "vacant",
                email=page["email"],
                page_url=page["page_url"],
                offices=page["offices"],
                committees=page["committees"],
                term_start=seat["term_start"] if seat else None,
                term_end=seat["term_end"] if seat else None,
                seat_conflict=seat_conflict,
            )
            if (seat or name)
            else None
        )

        districts.append(
            District(
                number=number,
                neighborhoods=page["neighborhoods"],
                member=member,
                boards=boards_by_district.get(number, ()),
                provenance={
                    "member": f"council.nyc.gov/district-{number}/ @ {seen_at}",
                    "seat_status": f"NYC Open Data uvw5-9znb @ {seen_at}",
                    "community_boards": f"NYC Open Data ruf7-3wgc + 5crt-au7u geometry @ {seen_at}",
                },
                missing=tuple(page["missing"]),
            )
        )
    return districts, current, boards_by_code


def build_site(raw_dir: Path, out_dir: Path, *, today: date | None = None) -> dict:
    """Build into a temporary directory, then swap it in.

    Building in place would leave a broken site visible if rendering failed
    halfway; building aside and swapping makes the publish atomic enough that a
    reader never sees a partial site.
    """
    raw = Path(raw_dir)
    out = Path(out_dir)
    day = today or date.today()
    now = datetime.now()

    calendar_html = (raw / "legistar_calendar.html").read_text(encoding="utf-8", errors="replace")
    meetings = parse_calendar(calendar_html)
    _check_floor("calendar", len(meetings))

    districts, _, boards_by_code = _load_districts(raw, day)

    ahead = upcoming(meetings, day, SHORTLIST_SIZE)
    window_end = max((m.date for m in meetings), default=None)

    staging = out.with_name(out.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    (staging / "index.html").write_text(
        render_index(
            districts,
            sorted(boards_by_code.values(), key=lambda b: b.code),
            built_at=now,
            window_end=window_end,
        ),
        encoding="utf-8",
    )
    (staging / "404.html").write_text(
        render_not_found(built_at=now, window_end=window_end), encoding="utf-8"
    )

    # /district/ exists so that a no-JavaScript form submit lands somewhere
    # useful instead of a 404.
    district_root = staging / "district"
    district_root.mkdir()
    (district_root / "index.html").write_text(
        render_index(
            districts,
            sorted(boards_by_code.values(), key=lambda b: b.code),
            built_at=now,
            window_end=window_end,
        ),
        encoding="utf-8",
    )

    for district in districts:
        page_dir = district_root / str(district.number)
        page_dir.mkdir()
        (page_dir / "index.html").write_text(
            render_district(
                district, ahead, built_at=now, window_end=window_end, today=day, now=now
            ),
            encoding="utf-8",
        )

    # The 59 community board pages. A board is a different view, not a variant of
    # a district: it has a standing monthly cadence, a zoning review role, and it
    # seats members of the public on committees.
    repo_root = Path(__file__).resolve().parents[2]
    boards_to_districts = load_boards_to_districts(repo_root / CROSSWALK_PATH)
    board_root = staging / "board"
    board_root.mkdir()
    boards_written = 0
    for code, board in sorted(boards_by_code.items()):
        page_dir = board_root / code
        page_dir.mkdir()
        (page_dir / "index.html").write_text(
            render_board(
                board,
                boards_to_districts.get(code, []),
                built_at=now,
                window_end=window_end,
            ),
            encoding="utf-8",
        )
        boards_written += 1
    if boards_written != 59:
        raise BuildError(f"wrote {boards_written} board pages, expected 59")
    (board_root / "index.html").write_text(
        render_index(
            districts,
            sorted(boards_by_code.values(), key=lambda b: b.code),
            built_at=now,
            window_end=window_end,
        ),
        encoding="utf-8",
    )

    # Geometry for the address box. The city geocoder returns a coordinate but
    # NOT a council district, so the browser has to do the point-in-polygon itself.
    # Shipped simplified: 132 KB gzipped against 3.8 MB raw, measured to assign the
    # same district as full precision on 99.99% of a citywide lattice
    # (tests/unit/test_geo.py::TestSimplifiedGeometryAgrees).
    data_dir = staging / "data"
    data_dir.mkdir()
    council_polygons = load_features(raw / "districts.geojson", "coundist")
    if len(council_polygons) != DISTRICT_COUNT:
        raise BuildError(
            f"district geometry has {len(council_polygons)} features, expected {DISTRICT_COUNT}"
        )
    (data_dir / "districts.geo.json").write_text(
        json.dumps(to_geojson(council_polygons, "coundist"), separators=(",", ":")),
        encoding="utf-8",
    )

    # Everything resolvable without the network: a district number, a neighbourhood
    # name, a board name, or a ZIP. Typing one of these must never reach the
    # geocoder — it is faster and it keeps the input on the machine.
    zips = load_zips(repo_root / CROSSWALK_PATH)
    lookup = {
        "districts": [{"n": d.number, "hoods": d.neighborhoods or ""} for d in districts],
        "boards": [
            {"code": b.code, "label": b.label, "hoods": b.neighborhoods or ""}
            for b in sorted(boards_by_code.values(), key=lambda b: b.code)
        ],
        "zips": {code: [n for n, _ in pairs] for code, pairs in sorted(zips.items())},
    }
    (data_dir / "lookup.json").write_text(
        json.dumps(lookup, separators=(",", ":")), encoding="utf-8"
    )

    assets_src = Path(__file__).parent / "assets"
    shutil.copytree(assets_src, staging / "assets")

    headers = Path(__file__).resolve().parents[2] / "_headers"
    if headers.exists():
        shutil.copy2(headers, staging / "_headers")

    manifest = Manifest(
        sources={
            "legistar_calendar": {
                "fetched_at": _mtime(raw / "legistar_calendar.html"),
                "max_age_hours": 12,
                "rows": len(meetings),
            },
            "district_pages": {
                "fetched_at": _mtime(raw / "district_pages.json"),
                "max_age_hours": 24 * 40,
                "rows": DISTRICT_COUNT,
            },
            "members": {
                "fetched_at": _mtime(raw / "members.json"),
                "max_age_hours": 24 * 40,
                "rows": DISTRICT_COUNT,
            },
            "community_boards": {
                "fetched_at": _mtime(raw / "community_boards.json"),
                "max_age_hours": 24 * 90,
                "rows": 59,
            },
        },
        built_at=now,
        calendar_window_end=window_end,
    )
    (staging / "manifest.json").write_text(
        json.dumps(
            {
                "built_at": manifest.built_at.isoformat(timespec="seconds"),
                "calendar_window_end": window_end.isoformat() if window_end else None,
                "sources": manifest.sources,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)

    return {
        "districts": len(districts),
        "meetings_parsed": len(meetings),
        "shortlist": len(ahead),
        "window_end": window_end.isoformat() if window_end else None,
        "districts_with_gaps": sum(1 for d in districts if d.missing),
        "boards_linked": sum(len(d.boards) for d in districts),
        "board_pages": len(boards_by_code),
        "zip_codes": len(zips),
        "boards_without_email": sum(1 for d in districts for b in d.boards if b.email is None),
        "vacant_seats": [
            d.number for d in districts if d.member and d.member.seat_status == "vacant"
        ],
        "out": str(out),
    }


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
