"""Point-in-polygon and the overlap sweep.

The synthetic cases pin the algorithm's edges (holes, shared edges, vertices on
the ray). The real-geometry cases are marked `slow` because the full sweep takes
~35 seconds, which is why the crosswalk is a committed file rather than a build
step.
"""

from __future__ import annotations

import json

from showup.geo import Polygon, load_features, locate, overlap_shares

SQUARE = [[(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]]
#: A square with a square hole, to prove even-odd fill handles interior rings.
DONUT = [
    [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)],
    [(3.0, 3.0), (3.0, 7.0), (7.0, 7.0), (7.0, 3.0), (3.0, 3.0)],
]


class TestContains:
    def test_interior_point(self):
        assert Polygon("a", SQUARE).contains(5.0, 5.0)

    def test_exterior_point(self):
        assert not Polygon("a", SQUARE).contains(15.0, 5.0)

    def test_bbox_rejects_cheaply(self):
        polygon = Polygon("a", SQUARE)
        assert not polygon.may_contain(-1.0, 5.0)
        assert polygon.may_contain(5.0, 5.0)

    def test_hole_reads_as_outside(self):
        polygon = Polygon("a", DONUT)
        assert polygon.contains(1.0, 5.0), "inside the ring, outside the hole"
        assert not polygon.contains(5.0, 5.0), "inside the hole"

    def test_vertex_on_the_ray_is_not_double_counted(self):
        # A ray passing exactly through a vertex is the classic way ray casting
        # flips a point to the wrong side.
        triangle = [[(0.0, 0.0), (5.0, 5.0), (10.0, 0.0), (0.0, 0.0)]]
        polygon = Polygon("t", triangle)
        assert polygon.contains(5.0, 1.0)
        assert not polygon.contains(5.0, 6.0)

    def test_adjacent_polygons_do_not_both_claim_a_shared_edge_point(self):
        left = Polygon("L", [[(0.0, 0.0), (0.0, 10.0), (5.0, 10.0), (5.0, 0.0), (0.0, 0.0)]])
        right = Polygon("R", [[(5.0, 0.0), (5.0, 10.0), (10.0, 10.0), (10.0, 0.0), (5.0, 0.0)]])
        on_edge = (5.0, 5.0)
        assert [p.key for p in (left, right) if p.contains(*on_edge)] != ["L", "R"]


class TestLocate:
    def test_returns_the_containing_key(self):
        polygons = [
            Polygon("L", [[(0.0, 0.0), (0.0, 10.0), (5.0, 10.0), (5.0, 0.0), (0.0, 0.0)]]),
            Polygon("R", [[(5.0, 0.0), (5.0, 10.0), (10.0, 10.0), (10.0, 0.0), (5.0, 0.0)]]),
        ]
        assert locate(polygons, 2.0, 5.0) == "L"
        assert locate(polygons, 8.0, 5.0) == "R"

    def test_returns_none_outside_everything(self):
        assert locate([Polygon("a", SQUARE)], 99.0, 99.0) is None


class TestOverlapShares:
    def test_halves_are_detected(self):
        outer = [Polygon("D", SQUARE)]
        inner = [
            Polygon("left", [[(0.0, 0.0), (0.0, 10.0), (5.0, 10.0), (5.0, 0.0), (0.0, 0.0)]]),
            Polygon("right", [[(5.0, 0.0), (5.0, 10.0), (10.0, 10.0), (10.0, 0.0), (5.0, 0.0)]]),
        ]
        shares = overlap_shares(outer, inner, spacing=0.25, min_share=0.01)["D"]
        assert {key for key, _ in shares} == {"left", "right"}
        assert all(0.4 < share < 0.6 for _, share in shares)

    def test_slivers_are_dropped(self):
        outer = [Polygon("D", SQUARE)]
        inner = [
            Polygon("big", [[(0.0, 0.0), (0.0, 10.0), (9.5, 10.0), (9.5, 0.0), (0.0, 0.0)]]),
            Polygon("sliver", [[(9.5, 0.0), (9.5, 10.0), (10.0, 10.0), (10.0, 0.0), (9.5, 0.0)]]),
        ]
        shares = overlap_shares(outer, inner, spacing=0.25, min_share=0.10)["D"]
        assert [key for key, _ in shares] == ["big"]

    def test_ordered_by_descending_share(self):
        outer = [Polygon("D", SQUARE)]
        inner = [
            Polygon("small", [[(0.0, 0.0), (0.0, 10.0), (2.0, 10.0), (2.0, 0.0), (0.0, 0.0)]]),
            Polygon("large", [[(2.0, 0.0), (2.0, 10.0), (10.0, 10.0), (10.0, 0.0), (2.0, 0.0)]]),
        ]
        shares = overlap_shares(outer, inner, spacing=0.25, min_share=0.01)["D"]
        assert [key for key, _ in shares] == ["large", "small"]


class TestLoadFeatures:
    def test_excludes_requested_keys(self, tmp_path):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {"boro_cd": "101"},
                    "geometry": {"type": "Polygon", "coordinates": SQUARE},
                },
                {
                    "properties": {"boro_cd": "164"},
                    "geometry": {"type": "Polygon", "coordinates": SQUARE},
                },
            ],
        }
        path = tmp_path / "cd.geojson"
        path.write_text(json.dumps(payload))
        keys = {p.key for p in load_features(path, "boro_cd", exclude={"164"})}
        assert keys == {"101"}

    def test_multipolygon_rings_are_flattened(self, tmp_path):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {"coundist": "1"},
                    "geometry": {"type": "MultiPolygon", "coordinates": [SQUARE, SQUARE]},
                }
            ],
        }
        path = tmp_path / "c.geojson"
        path.write_text(json.dumps(payload))
        polygons = load_features(path, "coundist")
        assert len(polygons) == 1
        assert len(polygons[0].rings) == 2
