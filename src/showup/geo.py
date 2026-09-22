"""Point-in-polygon, and working out which community boards a council district covers.

Two jobs, both needed because the city publishes no crosswalk between council
districts and community districts:

1. `locate` — which council district contains a coordinate. Needed for the address
   path: `geosearch.planninglabs.nyc` returns a lat/lng but **not** a council
   district, so the assignment has to happen here.
2. `overlap_shares` — how much of each community district falls inside each
   council district.

WHY WE DO NOT USE `ruf7-3wgc.council_district`
The community-boards dataset has a `council_district` column, and using it would
be one line. It is wrong: 59 rows carry only 44 distinct values, and districts
5, 8, 15, 20, 27, 32 and 40 appear nowhere. The column is the council district of
the board's *office address*, not the districts the board covers — a board whose
office sits in one district commonly serves two or three. Joining on it would
leave seven council districts with no board at all and silently mis-state the rest.

WHY GRID SAMPLING RATHER THAN POLYGON INTERSECTION
True areal intersection needs a robust clipping implementation, which is a real
library (shapely) and this project ships zero runtime dependencies for security
reasons. Sampling a lattice and counting which pair each point falls in reuses the
ray-casting we already need for job 1, has no failure mode worse than a slightly
wrong *share*, and the ordering it produces — which board covers most of a
district — is stable well below the resolution we use. The shares are reported as
approximate because they are.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["GRID_SPACING_DEG", "Polygon", "load_features", "locate", "overlap_shares"]

#: Lattice spacing in degrees, about 110 m north-south at this latitude. Fine
#: enough that a board covering a meaningful slice of a council district is never
#: missed, coarse enough to keep the whole sweep near a second.
GRID_SPACING_DEG = 0.001

#: Boards smaller than this share of a council district are dropped from its list.
#: Council and community district lines were drawn independently, so almost every
#: pair of neighbours overlaps by a sliver; listing those would bury the two or
#: three boards that actually matter to a resident.
MIN_SHARE = 0.04


class Polygon:
    """One feature's rings plus a bounding box, prepared for repeated hit-testing.

    The bounding box is the whole optimisation: a citywide lattice against 51
    council districts is millions of candidate tests, and rejecting on four
    comparisons first turns that into a handful of real ones per point.
    """

    __slots__ = ("key", "max_x", "max_y", "min_x", "min_y", "rings")

    def __init__(self, key: str, rings: list[list[tuple[float, float]]]) -> None:
        self.key = key
        self.rings = rings
        xs = [x for ring in rings for x, _ in ring]
        ys = [y for ring in rings for _, y in ring]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)

    def may_contain(self, x: float, y: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y

    def contains(self, x: float, y: float) -> bool:
        """Ray casting with even-odd fill, so interior rings (holes) work.

        A point inside a hole crosses that ring's edges an even number of extra
        times and correctly reads as outside. Rings are not classified as outer or
        inner: even-odd makes that unnecessary.
        """
        if not self.may_contain(x, y):
            return False
        inside = False
        for ring in self.rings:
            count = len(ring)
            j = count - 1
            for i in range(count):
                xi, yi = ring[i]
                xj, yj = ring[j]
                # Half-open comparison on y avoids double-counting a vertex that
                # lies exactly on the ray, which is the classic source of
                # points flipping to the wrong side along a shared edge.
                if (yi > y) != (yj > y):
                    x_cross = xi + (y - yi) * (xj - xi) / (yj - yi)
                    if x < x_cross:
                        inside = not inside
                j = i
        return inside


def _rings(geometry: dict) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    if kind == "Polygon":
        return [[(float(x), float(y)) for x, y, *_ in ring] for ring in geometry["coordinates"]]
    if kind == "MultiPolygon":
        return [
            [(float(x), float(y)) for x, y, *_ in ring]
            for polygon in geometry["coordinates"]
            for ring in polygon
        ]
    return []


def load_features(
    path: Path, key_property: str, *, exclude: set[str] | None = None
) -> list[Polygon]:
    """Load a GeoJSON file into hit-testable polygons keyed on one property."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    skip = exclude or set()
    polygons: list[Polygon] = []
    for feature in data.get("features", []):
        key = str(feature.get("properties", {}).get(key_property, "")).strip()
        if not key or key in skip:
            continue
        rings = _rings(feature.get("geometry") or {})
        if rings:
            polygons.append(Polygon(key, rings))
    return polygons


def locate(polygons: list[Polygon], lon: float, lat: float) -> str | None:
    """The key of the first polygon containing the point, or None."""
    for polygon in polygons:
        if polygon.contains(lon, lat):
            return polygon.key
    return None


def overlap_shares(
    outer: list[Polygon],
    inner: list[Polygon],
    *,
    spacing: float = GRID_SPACING_DEG,
    min_share: float = MIN_SHARE,
) -> dict[str, list[tuple[str, float]]]:
    """For each `outer` polygon, the `inner` polygons covering it and their share.

    Returns {outer_key: [(inner_key, share), ...]} ordered by descending share,
    with slivers below `min_share` dropped. Shares are of the outer polygon's
    sampled area and sum to at most 1 (water and unsampled gaps mean they can sum
    to less, which is honest rather than normalised away).
    """
    min_x = min(p.min_x for p in outer)
    max_x = max(p.max_x for p in outer)
    min_y = min(p.min_y for p in outer)
    max_y = max(p.max_y for p in outer)

    tally: dict[str, dict[str, int]] = {p.key: {} for p in outer}
    totals: dict[str, int] = {p.key: 0 for p in outer}

    steps_y = int((max_y - min_y) / spacing) + 1
    steps_x = int((max_x - min_x) / spacing) + 1

    for iy in range(steps_y):
        y = min_y + iy * spacing
        # Re-filter by row: most polygons cannot contain any point on this
        # latitude, and skipping them here is what keeps the sweep fast.
        outer_row = [p for p in outer if p.min_y <= y <= p.max_y]
        if not outer_row:
            continue
        inner_row = [p for p in inner if p.min_y <= y <= p.max_y]
        for ix in range(steps_x):
            x = min_x + ix * spacing
            outer_key = None
            for polygon in outer_row:
                if polygon.contains(x, y):
                    outer_key = polygon.key
                    break
            if outer_key is None:
                continue
            totals[outer_key] += 1
            for polygon in inner_row:
                if polygon.contains(x, y):
                    counts = tally[outer_key]
                    counts[polygon.key] = counts.get(polygon.key, 0) + 1
                    break

    result: dict[str, list[tuple[str, float]]] = {}
    for key, counts in tally.items():
        total = totals[key]
        if not total:
            result[key] = []
            continue
        shares = [
            (inner_key, round(hits / total, 4))
            for inner_key, hits in counts.items()
            if hits / total >= min_share
        ]
        shares.sort(key=lambda pair: (-pair[1], pair[0]))
        result[key] = shares
    return result
