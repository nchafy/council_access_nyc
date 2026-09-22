"""Command line entry point.

    showup fetch [--only SOURCE] [--force]   refresh the upstream cache
    showup build [--raw etl/raw] [--out site]
    showup crosswalk                         regenerate the geometry crosswalk

Kept deliberately thin: it parses arguments, calls the module that does the work,
and reports. Anything worth testing lives in the modules it calls.

The report lines are not decoration — they are how a human notices drift, and they
are asserted in `tests/unit/test_cli.py`, because a change to one of them silently
failed to apply once and the board page count stopped printing for two commits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import BuildError, build_site
from .crosswalk import CrosswalkError, generate
from .fetch import SOURCES, FetchError, fetch_all

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build(args: argparse.Namespace) -> int:
    raw = (REPO_ROOT / args.raw).resolve()
    out = (REPO_ROOT / args.out).resolve()
    if not raw.is_dir():
        print(f"error: no cached sources at {raw}", file=sys.stderr)
        print("run `showup fetch` first", file=sys.stderr)
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
    print(f"  zip codes       : {report['zip_codes']}")
    if report["vacant_seats"]:
        print(f"  vacant seats    : {report['vacant_seats']}")
    return 0


def _fetch(args: argparse.Namespace) -> int:
    raw = (REPO_ROOT / args.raw).resolve()
    if args.only is None and not args.force:
        # Without this, a first-time run looks like a hang for eight minutes.
        print("refreshing the cache (district pages take ~8.5 min at the rate")
        print("council.nyc.gov's robots.txt asks for; skipped if already fresh)")

    try:
        report = fetch_all(raw, only=args.only, force=args.force)
    except FetchError as error:
        # Nothing ran at all, which is different from a source failing mid-run.
        print(f"fetch refused: {error}", file=sys.stderr)
        return 2

    fetched = [name for name, r in report["sources"].items() if r["status"] == "fetched"]
    fresh = [name for name, r in report["sources"].items() if r["status"] == "fresh"]
    print(f"fetched {len(fetched)}, already fresh {len(fresh)}, failed {len(report['failed'])}")
    if report["failed"]:
        print(f"  failed: {', '.join(report['failed'])}", file=sys.stderr)
        # The operator must be told the cache still holds the last good copies, or
        # they will assume the site is now broken.
        print("  previous cached copies were kept", file=sys.stderr)
        return 1
    return 0


def _crosswalk(args: argparse.Namespace) -> int:
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


#: A table rather than a chain of `if`s. There is then no unreachable "unknown
#: command" branch to leave untested, and adding a subcommand without a handler
#: raises a KeyError loudly instead of silently returning an exit code.
HANDLERS = {"build": _build, "fetch": _fetch, "crosswalk": _crosswalk}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="showup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build the static site from cached sources")
    build.add_argument("--raw", default="etl/raw", help="directory of cached upstream payloads")
    build.add_argument("--out", default="site", help="output directory")

    grab = sub.add_parser("fetch", help="refresh the upstream cache in etl/raw/")
    grab.add_argument("--raw", default="etl/raw")
    grab.add_argument(
        "--only",
        choices=[s.name for s in SOURCES],
        help="refresh a single source instead of all of them",
    )
    grab.add_argument("--force", action="store_true", help="refetch even if the cache is fresh")

    cross = sub.add_parser(
        "crosswalk",
        help="regenerate the council-district -> community-board crosswalk (slow, rare)",
    )
    cross.add_argument("--raw", default="etl/raw")
    cross.add_argument("--out", default="crosswalks/council_to_boards.json")

    args = parser.parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":  # pragma: no cover - entry point, run via the console script
    raise SystemExit(main())
