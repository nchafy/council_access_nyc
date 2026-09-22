"""Command line entry point.

    showup build [--raw etl/raw] [--out site]

Kept deliberately thin: it parses arguments, calls `build_site`, and reports.
Anything worth testing lives in the modules it calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import BuildError, build_site
from .crosswalk import CrosswalkError, generate

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="showup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build the static site from cached sources")
    build.add_argument("--raw", default="etl/raw", help="directory of cached upstream payloads")
    build.add_argument("--out", default="site", help="output directory")

    cross = sub.add_parser(
        "crosswalk",
        help="regenerate the council-district -> community-board crosswalk (slow, rare)",
    )
    cross.add_argument("--raw", default="etl/raw")
    cross.add_argument("--out", default="crosswalks/council_to_boards.json")

    args = parser.parse_args(argv)

    if args.command == "build":
        raw = (REPO_ROOT / args.raw).resolve()
        out = (REPO_ROOT / args.out).resolve()
        if not raw.is_dir():
            print(f"error: no cached sources at {raw}", file=sys.stderr)
            return 2
        try:
            report = build_site(raw, out)
        except BuildError as error:
            # Fail closed: say what broke, leave the previous site alone.
            print(f"build refused: {error}", file=sys.stderr)
            return 1

        print(
            f"built {report['districts']} district pages and "
            f"{report['board_pages']} board pages -> {report['out']}"
        )
        print(f"  meetings parsed : {report['meetings_parsed']}")
        print(f"  shortlist shown : {report['shortlist']}")
        print(f"  calendar through: {report['window_end']}")
        print(f"  pages with gaps : {report['districts_with_gaps']}")
        print(
            f"  board links     : {report['boards_linked']} "
            f"({report['boards_without_email']} without a publishable email)"
        )
        if report["vacant_seats"]:
            print(f"  vacant seats    : {report['vacant_seats']}")
        return 0

    if args.command == "crosswalk":
        raw = (REPO_ROOT / args.raw).resolve()
        out = (REPO_ROOT / args.out).resolve()
        print("sweeping the city lattice — this takes about 35 seconds")
        try:
            data = generate(
                raw / "districts.geojson",
                raw / "community_districts.geojson",
                raw / "modzcta.geojson",
            )
        except CrosswalkError as error:
            print(f"crosswalk refused: {error}", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        counts = [len(v) for v in data["districts"].values()]
        print(f"wrote {out}")
        print(
            f"  districts: {len(counts)}   boards per district: "
            f"min {min(counts)}, max {max(counts)}, mean {sum(counts) / len(counts):.1f}"
        )
        print(f"  zip codes: {len(data.get('zips') or {})}")
        print("  read the diff before committing it")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
