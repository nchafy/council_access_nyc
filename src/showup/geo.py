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


# --------------------------------------------------------------------------- #
# Simplification, for shipping geometry to a browser
# --------------------------------------------------------------------------- #

#: Douglas-Peucker tolerance in degrees, ~2.2 m. Chosen by measurement, not taste.
#: Measured over a 37,000-point citywide lattice, comparing the district each point
#: resolves to against the full-precision geometry:
#:
#:     tolerance   gzipped   points assigned to the WRONG district
#:     11 m         60 KB    0.059%
#:     2.2 m       132 KB    0.011%   <- chosen
#:     none        372 KB    0.005%
#:
#: The floor is not zero: even unsimplified geometry disagrees on 2 points, which
#: are lattice points sitting exactly on a shared edge — an artifact of the
#: comparison rather than of simplification. So 2.2 m is close to as good as this
#: gets, at a third of the 300 KB payload budget. Going coarser is a fivefold
#: accuracy cost for 72 KB, which is the wrong trade for a page whose whole claim
#: is "this is your council member".
#:
#: Boundary cases remain possible, which is why the address result always offers
#: the City's own lookup as the authority — our geometry is a copy of DCP's
#: published lines, not the legal definition of a district.
SIMPLIFY_TOLERANCE_DEG = 0.00002

#: Coordinate precision. 5 decimals is ~1 m, well below any boundary's accuracy,
#: and truncating there is most of the file-size win.
COORD_PRECISION = 5


def _perpendicular_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def simplify_ring(ring: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker, iterative.

    Iterative rather than recursive because a single coastline ring runs to tens of
    thousands of vertices and the recursive form blows the stack on real input.
    """
    if len(ring) <= 3:
        return list(ring)

    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        first, last = stack.pop()
        worst = -1.0
        index = -1
        for i in range(first + 1, last):
            distance = _perpendicular_distance(ring[i], ring[first], ring[last])
            if distance > worst:
                worst, index = distance, i
        if worst > tolerance and index != -1:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [point for point, keeper in zip(ring, keep, strict=True) if keeper]


def simplify_rings(
    rings: list[list[tuple[float, float]]],
    *,
    tolerance: float = SIMPLIFY_TOLERANCE_DEG,
    precision: int = COORD_PRECISION,
) -> list[list[tuple[float, float]]]:
    """Simplify and round every ring, dropping any that collapses.

    A ring needs four positions to be a valid closed ring. Islands smaller than
    the tolerance disappear — an accepted trade, since they are also too small to
    contain a distinguishable address at this precision, and the agreement test
    would fail if the loss mattered.
    """
    out: list[list[tuple[float, float]]] = []
    for ring in rings:
        simplified = simplify_ring(ring, tolerance)
        rounded = [(round(x, precision), round(y, precision)) for x, y in simplified]
        deduped = [p for i, p in enumerate(rounded) if i == 0 or p != rounded[i - 1]]
        if deduped and deduped[0] != deduped[-1]:
            deduped.append(deduped[0])
        if len(deduped) >= 4:
            out.append(deduped)
    return out


def to_geojson(
    polygons: list[Polygon],
    key_property: str,
    *,
    simplify: bool = True,
    tolerance: float | None = None,
    precision: int = COORD_PRECISION,
) -> dict:
    """Serialise polygons back to GeoJSON, optionally simplified for the browser.

    Every feature becomes a MultiPolygon of its rings. We do not attempt to
    reconstruct the original outer/inner nesting: the browser's hit test uses the
    same even-odd rule as `Polygon.contains`, so a flat ring list is equivalent for
    our purpose and simpler to be correct about.
    """
    features = []
    for polygon in sorted(polygons, key=lambda p: p.key):
        rings = (
            simplify_rings(
                polygon.rings,
                tolerance=SIMPLIFY_TOLERANCE_DEG if tolerance is None else tolerance,
                precision=precision,
            )
            if simplify
            else polygon.rings
        )
        if not rings:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {key_property: polygon.key},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[list(map(list, ring))] for ring in rings],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
