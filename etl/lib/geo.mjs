// Geometry helpers for shipping the 51 council-district boundaries to a browser.
//
// The city's GeoJSON (872g-cjhh, water areas included) is 3.8 MB. Most of that is
// coastline traced at sub-metre precision, which is invisible at the zoom levels
// a citywide map uses and expensive to parse on a phone. We simplify with
// Ramer-Douglas-Peucker and drop coordinate precision to ~1 m.
//
// Simplification is done here, at build time, rather than in the browser: the
// client also needs these polygons for point-in-polygon address lookup, and we
// want the shape it tests against to be exactly the shape it draws.

/** Perpendicular distance from p to the segment ab, in degrees. */
function perpDistance(p, a, b) {
  const [px, py] = p;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
  const clamped = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + clamped * dx), py - (ay + clamped * dy));
}

/**
 * Ramer-Douglas-Peucker, iterative so a 40k-vertex coastline ring cannot blow
 * the call stack.
 * @param {number[][]} points
 * @param {number} tolerance in degrees
 */
export function simplifyLine(points, tolerance) {
  if (points.length <= 2) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;

  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let maxDist = -1;
    let index = -1;
    for (let i = first + 1; i < last; i++) {
      const d = perpDistance(points[i], points[first], points[last]);
      if (d > maxDist) {
        maxDist = d;
        index = i;
      }
    }
    if (maxDist > tolerance && index !== -1) {
      keep[index] = 1;
      stack.push([first, index], [index, last]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

const roundTo = (n, places) => {
  const f = 10 ** places;
  return Math.round(n * f) / f;
};

/**
 * Simplify one linear ring, keeping it closed and keeping it a valid ring
 * (>= 4 positions). Returns null if the ring collapses to nothing meaningful.
 */
function simplifyRing(ring, tolerance, precision) {
  let out = simplifyLine(ring, tolerance).map(([x, y]) => [roundTo(x, precision), roundTo(y, precision)]);

  // Rounding can create consecutive duplicates; drop them.
  out = out.filter((p, i) => i === 0 || p[0] !== out[i - 1][0] || p[1] !== out[i - 1][1]);

  // Re-close the ring if simplification or rounding broke the closure.
  const first = out[0];
  const last = out[out.length - 1];
  if (!first) return null;
  if (first[0] !== last[0] || first[1] !== last[1]) out.push([first[0], first[1]]);

  return out.length >= 4 ? out : null;
}

/**
 * Simplify a Polygon or MultiPolygon geometry in place-safe fashion.
 * Rings that collapse are dropped; a polygon whose outer ring collapses is
 * dropped entirely. Islands smaller than the tolerance disappear, which is the
 * intended trade — they are not clickable at citywide zoom anyway.
 */
export function simplifyGeometry(geometry, { tolerance = 0.00012, precision = 5 } = {}) {
  const doPolygon = (poly) => {
    const rings = [];
    for (let i = 0; i < poly.length; i++) {
      const simplified = simplifyRing(poly[i], tolerance, precision);
      if (!simplified) {
        // Outer ring gone means the whole polygon is gone.
        if (i === 0) return null;
        continue;
      }
      rings.push(simplified);
    }
    return rings.length ? rings : null;
  };

  if (geometry.type === 'Polygon') {
    const rings = doPolygon(geometry.coordinates);
    return rings ? { type: 'Polygon', coordinates: rings } : null;
  }
  if (geometry.type === 'MultiPolygon') {
    const polys = geometry.coordinates.map(doPolygon).filter(Boolean);
    return polys.length ? { type: 'MultiPolygon', coordinates: polys } : null;
  }
  return geometry;
}

/** Count positions in a geometry, for reporting how much we saved. */
export function countPositions(geometry) {
  if (!geometry) return 0;
  const ringCount = (rings) => rings.reduce((n, r) => n + r.length, 0);
  if (geometry.type === 'Polygon') return ringCount(geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.reduce((n, p) => n + ringCount(p), 0);
  return 0;
}

/** Bounding box [minX, minY, maxX, maxY] of a geometry. */
export function bbox(geometry) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const visit = (rings) => {
    for (const ring of rings) {
      for (const [x, y] of ring) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  };
  if (geometry.type === 'Polygon') visit(geometry.coordinates);
  else if (geometry.type === 'MultiPolygon') geometry.coordinates.forEach(visit);
  return [minX, minY, maxX, maxY];
}

/** Rough centroid (area-weighted over outer rings) for label placement. */
export function centroid(geometry) {
  const polys = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
  let cxSum = 0;
  let cySum = 0;
  let areaSum = 0;
  for (const poly of polys) {
    const ring = poly[0];
    let area = 0;
    let cx = 0;
    let cy = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const cross = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
      area += cross;
      cx += (ring[j][0] + ring[i][0]) * cross;
      cy += (ring[j][1] + ring[i][1]) * cross;
    }
    area /= 2;
    if (area === 0) continue;
    cxSum += cx / (6 * area) * Math.abs(area);
    cySum += cy / (6 * area) * Math.abs(area);
    areaSum += Math.abs(area);
  }
  if (!areaSum) {
    const [minX, minY, maxX, maxY] = bbox(geometry);
    return [(minX + maxX) / 2, (minY + maxY) / 2];
  }
  return [cxSum / areaSum, cySum / areaSum];
}
