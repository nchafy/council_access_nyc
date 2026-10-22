// The map on the front page. Two layers — the 51 council districts and the 59 community
// boards — with one visible at a time, because they answer different questions and
// overlaying them makes both unreadable.
//
// MapLibre is 449 KB gzipped against a 12 KB script ceiling, so it is imported dynamically
// and only after the document has painted: the address box, the dropdowns and the link
// lists all work before a byte of it arrives. No basemap — tiles would be a third-party
// request disclosing which neighbourhood is being read, which product-brief.md §5 refuses.
// Every polygon in a layer carries the same fill; the only one that differs is the one the
// reader selected, because a shaded map reads as a ranking whatever the legend says.

const container = document.getElementById('map');
const status = document.getElementById('map-status');
const toggle = document.getElementById('map-toggle');

// OpenFreeMap, which publishes no SLA, so `FALLBACK_STYLE` is not decoration: when the
// style request fails the districts must still draw and hit-test (outline §"Failure and
// staleness behaviour"). Adding this host withdrew the no-third-party promise, recorded as
// an owner decision in product-brief.md §5.
//: Overridden by `data-basemap` on the container, which is where the choice actually
//: lives; this is the fallback if the attribute is missing.
const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';

//: Esri's Light Gray Canvas, as howfar.nyc uses it: a raster base plus a separate label
//: layer, which is why its labels sit above an overlay. Selected with
//: `data-basemap="esri-light-gray"`.
//:
//: NOT the default, and the reason is licensing rather than looks. `server.arcgisonline.com`
//: is Esri's commercial ArcGIS Online service. The keyless endpoints are widely used — they
//: ship as a Leaflet provider preset — but Esri's terms govern ArcGIS Online basemaps and
//: generally contemplate an account for application use. Nobody here has confirmed this use
//: is licensed. Attribution to Esri is required and is set on the source below.
const ESRI_TILE = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const ESRI_LIGHT_GRAY = {
  version: 8,
  sources: {
    'esri-base': {
      type: 'raster',
      tiles: [`${ESRI_TILE}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      attribution: 'Tiles &copy; Esri — Esri, DeLorme, NAVTEQ',
    },
    'esri-reference': {
      type: 'raster',
      tiles: [`${ESRI_TILE}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
    },
  },
  // The reference layer is added after the districts in `draw`, so labels stay on top.
  layers: [{ id: 'esri-base', type: 'raster', source: 'esri-base' }],
};

//: Styles this module knows by name rather than by URL.
const NAMED_STYLES = { 'esri-light-gray': ESRI_LIGHT_GRAY };
//: Source layers dropped from the basemap before MapLibre ever sees it. Roads at the same
//: visual weight as a district boundary mean neither reads, and the point of a basemap under
//: a data overlay is to recede. `transportation` is the 20 road and pier layers;
//: `transportation_name` is the 6 road labels and highway shields. What survives is water,
//: waterways, parks, landuse, buildings, administrative boundaries and place labels — enough
//: to know where you are without competing with the thing being shown.
const DROPPED_SOURCE_LAYERS = new Set(['transportation', 'transportation_name']);

const FALLBACK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f6f7f9' } }],
};

const FILL = '#9db8d2';
const SELECTED = '#2b5f93';
const HOVERED = '#7fa0c4';
const LINE = '#31506f';

const BOROUGHS = {
  1: 'Manhattan',
  2: 'The Bronx',
  3: 'Brooklyn',
  4: 'Queens',
  5: 'Staten Island',
};

function boroughOf(code) {
  return BOROUGHS[String(code).charAt(0)] || 'New York City';
}

/** The two layers, and everything that differs between them, in one place. */
const LAYERS = {
  council: {
    url: '/data/districts.geo.json',
    key: 'coundist',
    source: 'council',
    noun: 'council district',
    href: (id) => `/district/${id}/`,
    label: (id) => `Council District ${id}`,
    // "drawn to equal population" was asserted here and cut 2026-10-22: the criteria are in
    // City Charter §52 and were never read, so the card states who draws the lines and when,
    // which nyc.gov/site/districting does say.
    facts: (id) => [
      ['District', String(id)],
      ['Boundaries', 'Set by the NYC Districting Commission, redrawn every 10 years'],
    ],
  },
  board: {
    url: '/data/boards.geo.json',
    key: 'boro_cd',
    source: 'board',
    noun: 'community board',
    href: (id) => `/board/${id}/`,
    // `302` is Brooklyn's board 2: the first digit is the borough, the rest the board,
    // and the leading zero is padding rather than part of the number.
    label: (id) => `Community Board ${Number(String(id).slice(1))}, ${boroughOf(id)}`,
    facts: (id) => [
      ['Borough', boroughOf(id)],
      ['Board', String(Number(String(id).slice(1)))],
      ['Code', String(id)],
    ],
  },
};

function say(text) {
  if (status) status.textContent = text;
}

// WebGL2 before MapLibre: a 449 KB download that can only fail is worth skipping, and
// every answer on this page is reachable without it.
function hasWebgl2() {
  try {
    return Boolean(document.createElement('canvas').getContext('webgl2'));
  } catch {
    return false;
  }
}

/** Resolve after first paint, so the map never delays the content above it. */
function afterFirstPaint() {
  return new Promise((resolve) => {
    if (document.readyState === 'complete') {
      requestAnimationFrame(() => resolve());
      return;
    }
    window.addEventListener('load', () => requestAnimationFrame(() => resolve()), {
      once: true,
    });
  });
}

/** The id of the basemap's first label layer, or undefined if it has none.
 *
 * Our district layers are inserted before it, so place and water names draw *on top of*
 * the overlay instead of under it. This is the trick Esri's Light Gray Canvas gets by
 * shipping its labels as a second tile layer; with a vector style it is one argument.
 */
function firstLabelLayerId(style) {
  const label = (style.layers || []).find((layer) => layer.type === 'symbol');
  return label && label.id;
}

/** The basemap style with its road layers removed, or null if it could not be had. */
async function loadBasemapStyle(url) {
  // A named style is ours already; there is nothing to fetch and no roads to strip.
  if (NAMED_STYLES[url]) return NAMED_STYLES[url];
  try {
    const style = await fetchJson(url);
    const kept = (style.layers || []).filter(
      (layer) => !DROPPED_SOURCE_LAYERS.has(layer['source-layer'])
    );
    // Filtered here rather than hidden after load, so the roads never paint at all and
    // there is no flash of them on a slow connection.
    return { ...style, layers: kept };
  } catch {
    return null;
  }
}

function fetchJson(url) {
  return fetch(url).then((response) => {
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json();
  });
}

async function main() {
  if (!container) return;
  if (!hasWebgl2()) {
    say('This browser has no WebGL, so the map cannot draw. Everything is listed below.');
    return;
  }

  await afterFirstPaint();
  say('Loading the map…');

  let MapLibre;
  let geometry;
  let basemap;
  try {
    const [library, council, board, style] = await Promise.all([
      import('/vendor/maplibre-gl.mjs'),
      fetchJson(LAYERS.council.url),
      fetchJson(LAYERS.board.url),
      loadBasemapStyle(container.dataset.basemap || BASEMAP_STYLE),
    ]);
    MapLibre = library;
    geometry = { council, board };
    basemap = style;
  } catch (error) {
    // Named, not swallowed: a reader who sees nothing should be told whose fault it is.
    say(`The map could not load (${error.message}). Everything is listed below.`);
    return;
  }

  const map = new MapLibre.Map({
    container,
    // The style object, already stripped of roads. Null when the host could not be
    // reached, which is what OpenFreeMap publishing no SLA means in practice.
    style: basemap || FALLBACK_STYLE,
    center: [-73.95, 40.7],
    zoom: 9,
    attributionControl: false,
    // The boundaries are the content; tilting or spinning them helps nobody read one.
    pitchWithRotate: false,
    dragRotate: false,
    touchZoomRotate: false,
  });

  // A style that 404s or times out arrives here, not at `load`, so the fallback is armed
  // before the first paint rather than after a reader has stared at nothing.
  let usingFallback = false;
  map.on('error', (event) => {
    const message = (event && event.error && event.error.message) || 'unknown error';
    if (!usingFallback && /style|sprite|glyph|tiles\.openfreemap/i.test(message)) {
      usingFallback = true;
      say('The basemap did not load, so the districts are drawn on their own.');
      map.setStyle(FALLBACK_STYLE);
      return;
    }
    if (!usingFallback) {
      say(`The map reported an error (${message}). Everything is listed below.`);
    }
  });

  const draw = () => {
    const beforeId = basemap ? firstLabelLayerId(map.getStyle()) : undefined;
    for (const name of Object.keys(LAYERS)) {
      addLayer(map, LAYERS[name], geometry[name], beforeId);
    }
    // Esri ships its labels as their own tile layer, so they go on last to sit above the
    // districts. A vector style needs no equivalent: `beforeId` above does the same job.
    if (map.getSource('esri-reference') && !map.getLayer('esri-reference')) {
      map.addLayer({ id: 'esri-reference', type: 'raster', source: 'esri-reference' });
    }

    const bounds = geometryBounds(geometry.council);
    if (bounds) map.fitBounds(bounds, { padding: 24, animate: false });

    const view = new View(map);
    view.show('council');
    bindToggle(view);
    bindZoom(map);
    bindSelection(view);
    bindAddress(view);
  };

  // `styledata` rather than `load`, because `setStyle` discards every layer we added and
  // fires it again; `load` fires once and would leave the fallback empty.
  map.on('styledata', () => {
    if (map.getSource('council')) return;
    draw();
  });
}

function addLayer(map, layer, data, beforeId) {
  // promoteId is what makes setFeatureState addressable: these features carry no id of
  // their own, only the one key property.
  map.addSource(layer.source, { type: 'geojson', data, promoteId: layer.key });
  map.addLayer({
    id: `${layer.source}-fill`,
    type: 'fill',
    source: layer.source,
    layout: { visibility: 'none' },
    paint: {
      // Three states, most specific first: a selected polygon stays selected while the
      // pointer is over it, so hovering cannot hide what was chosen.
      'fill-color': [
        'case',
        ['boolean', ['feature-state', 'selected'], false],
        SELECTED,
        ['boolean', ['feature-state', 'hovered'], false],
        HOVERED,
        FILL,
      ],
      'fill-opacity': 0.45,
    },
  }, beforeId);
  map.addLayer({
    id: `${layer.source}-line`,
    type: 'line',
    source: layer.source,
    layout: { visibility: 'none' },
    paint: { 'line-color': LINE, 'line-width': 0.8 },
  }, beforeId);
}

/** Which layer is showing, and which feature in it is selected. */
class View {
  constructor(map) {
    this.map = map;
    this.name = 'council';
    this.selected = null;
  }

  get layer() {
    return LAYERS[this.name];
  }

  show(name) {
    if (!LAYERS[name]) return;
    this.clear();
    this.name = name;
    for (const other of Object.keys(LAYERS)) {
      const visibility = other === name ? 'visible' : 'none';
      this.map.setLayoutProperty(`${LAYERS[other].source}-fill`, 'visibility', visibility);
      this.map.setLayoutProperty(`${LAYERS[other].source}-line`, 'visibility', visibility);
    }
    say(`Showing ${this.layer.noun}s. Select one to open its page.`);
  }

  clear() {
    if (this.selected !== null) {
      this.map.setFeatureState(
        { source: this.layer.source, id: this.selected },
        { selected: false }
      );
    }
    this.selected = null;
    const card = document.getElementById('map-card');
    if (card) card.hidden = true;
  }

  select(id) {
    this.clear();
    this.selected = id;
    this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    this.fillCard(id);
    say(`${this.layer.label(id)} selected.`);
  }

  /** The selection card: what was selected, and the one link that opens it. */
  fillCard(id) {
    const card = document.getElementById('map-card');
    const title = document.getElementById('map-card-title');
    const facts = document.getElementById('map-card-facts');
    const link = document.getElementById('map-selection');
    if (!card || !title || !facts || !link) return;

    title.textContent = this.layer.label(id);
    // Built with DOM calls and textContent, never innerHTML: these values are ours, but
    // the rule in CLAUDE.md is that nothing reaches the page as markup.
    facts.replaceChildren();
    for (const [term, value] of this.layer.facts(id)) {
      const dt = document.createElement('dt');
      dt.textContent = term;
      const dd = document.createElement('dd');
      dd.textContent = value;
      facts.append(dt, dd);
    }
    link.textContent = `Open ${this.layer.label(id)}`;
    link.href = this.layer.href(id);
    card.hidden = false;
  }
}

function bindToggle(view) {
  if (!toggle) return;
  const buttons = [...toggle.querySelectorAll('[data-layer]')];
  for (const button of buttons) {
    button.addEventListener('click', () => {
      for (const other of buttons) other.setAttribute('aria-pressed', String(other === button));
      view.show(button.dataset.layer);
    });
  }
  toggle.hidden = false;
}

function bindZoom(map) {
  const group = document.getElementById('map-zoom');
  const zoomIn = document.getElementById('map-zoom-in');
  const zoomOut = document.getElementById('map-zoom-out');
  if (!group || !zoomIn || !zoomOut) return;
  zoomIn.addEventListener('click', () => map.zoomIn());
  zoomOut.addEventListener('click', () => map.zoomOut());
  group.hidden = false;
}

function bindSelection(view) {
  for (const name of Object.keys(LAYERS)) {
    const layer = LAYERS[name];
    const fill = `${layer.source}-fill`;
    let hovered = null;

    const setHover = (id) => {
      if (hovered === id) return;
      if (hovered !== null) {
        view.map.setFeatureState({ source: layer.source, id: hovered }, { hovered: false });
      }
      hovered = id;
      if (id !== null) {
        view.map.setFeatureState({ source: layer.source, id }, { hovered: true });
      }
    };

    view.map.on('mousemove', fill, (event) => {
      view.map.getCanvas().style.cursor = 'pointer';
      const feature = event.features && event.features[0];
      if (feature) setHover(feature.id ?? feature.properties[layer.key]);
    });
    view.map.on('mouseleave', fill, () => {
      view.map.getCanvas().style.cursor = '';
      setHover(null);
    });
    view.map.on('click', fill, (event) => {
      const feature = event.features && event.features[0];
      if (!feature) return;
      const id = feature.id ?? feature.properties[layer.key];
      if (id !== undefined && id !== null) view.select(String(id));
    });
  }
}

/** The address box dispatches; claiming the event is what stops the page navigating. */
function bindAddress(view) {
  document.addEventListener('showup:located', (event) => {
    const detail = event.detail || {};
    event.preventDefault();

    if (view.name === 'council' && detail.district) {
      view.select(String(detail.district));
      panTo(view, detail);
      return;
    }

    const hit = featureAt(view, detail);
    if (hit !== null) {
      view.select(String(hit));
      panTo(view, detail);
      return;
    }

    // A board cannot be derived from a district number: a district overlaps two or three
    // boards, so picking one would be a guess.
    say(
      view.name === 'board'
        ? 'That lookup gives a council district, and a district covers more than one board. ' +
            'Select a board on the map, or use the list below.'
        : 'Located, but the map could not place it.'
    );
  });
}

function featureAt(view, detail) {
  if (!Number.isFinite(detail.lon) || !Number.isFinite(detail.lat)) return null;
  const hits = view.map.queryRenderedFeatures(view.map.project([detail.lon, detail.lat]), {
    layers: [`${view.layer.source}-fill`],
  });
  const feature = hits && hits[0];
  if (!feature) return null;
  return feature.id ?? feature.properties[view.layer.key] ?? null;
}

function panTo(view, detail) {
  if (!Number.isFinite(detail.lon) || !Number.isFinite(detail.lat)) return;
  view.map.easeTo({ center: [detail.lon, detail.lat], zoom: 12, duration: 600 });
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
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}

main();
