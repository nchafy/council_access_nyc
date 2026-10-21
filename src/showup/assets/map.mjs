// The district map. MapLibre is 449 KB gzipped across three files, against a 12 KB script
// ceiling, so it is imported here and nowhere else: this module only exists on /map/, and
// the import is dynamic so a browser that cannot run the map never downloads it.
//
// No basemap. Tiles would be a third-party request disclosing which neighbourhood is being
// looked at, which product-brief.md §5 refuses. Every district carries the same fill,
// because a shaded map reads as a ranking whatever the legend says.

const container = document.getElementById('map');
const status = document.getElementById('map-status');

const FILL = '#9db8d2';
const SELECTED = '#3d6b99';
const LINE = '#31506f';

function say(text) {
  if (status) status.textContent = text;
}

// WebGL2 before MapLibre: a 449 KB download that can only fail is worth skipping, and the
// listed districts below already answer the question without it.
function hasWebgl2() {
  try {
    return Boolean(document.createElement('canvas').getContext('webgl2'));
  } catch {
    return false;
  }
}

async function main() {
  if (!container) return;
  if (!hasWebgl2()) {
    say('This browser has no WebGL, so the map cannot draw. The district list below works.');
    return;
  }

  say('Loading the map…');
  let MapLibre;
  let geometry;
  try {
    [MapLibre, geometry] = await Promise.all([
      import('/vendor/maplibre-gl.mjs'),
      fetch(container.dataset.geometry).then((response) => {
        if (!response.ok) throw new Error(`geometry ${response.status}`);
        return response.json();
      }),
    ]);
  } catch (error) {
    // Named, not swallowed: a reader who sees nothing should be told it is our fault.
    say(`The map could not load (${error.message}). The district list below works.`);
    return;
  }

  const map = new MapLibre.Map({
    container,
    // No sources and one background layer: the style is ours, so nothing is fetched.
    style: {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f6f7f9' } }],
    },
    // Overwritten by fitBounds once the geometry is in. Kept so a failure to fit still
    // lands on the city rather than the null island.
    center: [-73.95, 40.7],
    zoom: 9,
    attributionControl: false,
    // The districts are the content; tilting or spinning them helps nobody read a boundary.
    pitchWithRotate: false,
    dragRotate: false,
    touchZoomRotate: false,
  });

  map.on('error', (event) => {
    const message = (event && event.error && event.error.message) || 'unknown error';
    say(`The map reported an error (${message}). The district list below works.`);
  });

  map.on('load', () => {
    // `coundist` is the only property the geometry carries, and the features have no id of
    // their own, so promoting it is what makes `setFeatureState` addressable at all.
    map.addSource('districts', { type: 'geojson', data: geometry, promoteId: 'coundist' });
    map.addLayer({
      id: 'district-fill',
      type: 'fill',
      source: 'districts',
      paint: {
        'fill-color': ['case', ['boolean', ['feature-state', 'selected'], false], SELECTED, FILL],
        'fill-opacity': 0.85,
      },
    });
    map.addLayer({
      id: 'district-line',
      type: 'line',
      source: 'districts',
      paint: { 'line-color': LINE, 'line-width': 0.8 },
    });

    const bounds = geometryBounds(geometry);
    if (bounds) map.fitBounds(bounds, { padding: 12, animate: false });

    say('Select a district to open its page. Every district is also listed below.');
    bindSelection(map);
    bindZoom(map);
  });
}

/** Our own zoom buttons, revealed only once the map is actually drawing. */
function bindZoom(map) {
  const group = document.getElementById('map-zoom');
  const zoomIn = document.getElementById('map-zoom-in');
  const zoomOut = document.getElementById('map-zoom-out');
  if (!group || !zoomIn || !zoomOut) return;
  zoomIn.addEventListener('click', () => map.zoomIn());
  zoomOut.addEventListener('click', () => map.zoomOut());
  group.hidden = false;
}

/** The data's own bounding box, so the city fills the frame at any container size. */
function geometryBounds(geometry) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  const visit = (coordinates) => {
    if (typeof coordinates[0] === 'number') {
      const [longitude, latitude] = coordinates;
      if (longitude < west) west = longitude;
      if (longitude > east) east = longitude;
      if (latitude < south) south = latitude;
      if (latitude > north) north = latitude;
      return;
    }
    for (const part of coordinates) visit(part);
  };

  for (const feature of geometry.features || []) {
    if (feature.geometry && feature.geometry.coordinates) visit(feature.geometry.coordinates);
  }
  return Number.isFinite(west) ? [[west, south], [east, north]] : null;
}

function districtOf(feature) {
  const properties = feature && feature.properties;
  if (!properties) return null;
  const raw = properties.coundist;
  const number = Number.parseInt(raw, 10);
  return Number.isInteger(number) && number >= 1 && number <= 51 ? number : null;
}

function bindSelection(map) {
  let selected = null;

  const highlight = (id) => {
    if (selected !== null) {
      map.setFeatureState({ source: 'districts', id: selected }, { selected: false });
    }
    selected = id;
    if (id !== null) {
      map.setFeatureState({ source: 'districts', id }, { selected: true });
    }
  };

  map.on('mousemove', 'district-fill', (event) => {
    map.getCanvas().style.cursor = 'pointer';
    const feature = event.features && event.features[0];
    if (feature) highlight(feature.id ?? districtOf(feature));
  });

  map.on('mouseleave', 'district-fill', () => {
    map.getCanvas().style.cursor = '';
    highlight(null);
  });

  map.on('click', 'district-fill', (event) => {
    const feature = event.features && event.features[0];
    const number = districtOf(feature);
    if (number !== null) window.location.assign(`/district/${number}/`);
  });
}

main();
