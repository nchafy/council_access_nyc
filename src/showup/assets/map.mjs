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

//: Road layers kept despite their source layer being dropped. An early-2000s satnav screen is
//: *defined* by fat yellow arterials over saturated green, so dropping every road loses the
//: look entirely — but minor roads and paths were what made the districts unreadable, and
//: those stay out. Railways stay out too: a GPS unit drew roads, not timetables.
const KEPT_ROAD_LAYERS = new Set([
  'highway_motorway_casing',
  'highway_motorway_inner',
  'highway_motorway_bridge_casing',
  'highway_motorway_bridge_inner',
  'highway_major_casing',
  'highway_major_inner',
  'tunnel_motorway_casing',
  'tunnel_motorway_inner',
]);

//: Paint overrides applied to the basemap style after the roads come out. positron paints
//: parks `rgb(230,233,229)` on a `rgb(242,243,240)` background — a 12/255 difference, which
//: is why green space does not read on it at all. Greened here instead of switching to a
//: raster basemap, because raster labels blur on a 2x display and vector ones do not.
//: Layer-level overrides — zoom range, not paint. `landcover_wood` ships `minzoom: 10`, so at
//: the city-wide zoom this map opens at (about 9.6) the wooded part of Central Park and
//: Prospect Park is not drawn at all: only the `park` polygon is, and the woods appear as the
//: reader crosses zoom 10. That is the "piecewise" rendering. Esri's raster has no such seam
//: because its tiles are pre-drawn at every level.
const LAYER_OVERRIDES = {
  landcover_wood: { minzoom: 0 },
};

const PAINT_OVERRIDES = {
  // The satnav palette: land a flat olive-green, water a deep navy, parks a darker green,
  // arterials a bright yellow over a dark casing. Saturated on purpose — these screens were
  // read at a glance in daylight, which is why nothing on them was subtle.
  background: { 'background-color': '#cfd9a8' },
  landuse_residential: { 'fill-color': '#d8dfb2', 'fill-opacity': 0.85 },
  park: { 'fill-color': '#9ec27a' },
  landcover_wood: {
    'fill-color': '#8fb86c',
    // Woods faded in between zoom 8 and 12, so they appeared only once well zoomed in.
    // Flat, not a zoom ramp: the ramp faded woods in across zoom 8-12, which was the other
    // half of why one park appeared in pieces.
    'fill-opacity': 0.95,
  },
  landcover_glacier: { 'fill-color': '#e8eef2' },
  water: { 'fill-color': '#1b3f7a' },
  waterway: { 'line-color': '#1b3f7a' },
  building: { 'fill-color': '#c2ca9c', 'fill-opacity': 0.7 },
  highway_motorway_casing: { 'line-color': '#8a6b12' },
  highway_motorway_inner: { 'line-color': '#ffd23f' },
  highway_motorway_bridge_casing: { 'line-color': '#8a6b12' },
  highway_motorway_bridge_inner: { 'line-color': '#ffd23f' },
  tunnel_motorway_casing: { 'line-color': '#8a6b12' },
  tunnel_motorway_inner: { 'line-color': '#f3cf6a' },
  highway_major_casing: { 'line-color': '#9a7c1d' },
  highway_major_inner: { 'line-color': '#ffe27a' },
};

const FALLBACK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f6f7f9' } }],
};

//: The zoom window. The floor is computed per viewport — whatever zoom fits the whole city is
//: as far out as the map goes, so it can never be zoomed out to a continent. The ceiling is
//: fixed: past this the basemap has no more detail to give and the district boundary, which is
//: simplified to 2.2 m, starts to look like a decision rather than a coastline.
const MAX_ZOOM = 15;

const FILL = '#1b3f7a';
const SELECTED = '#e8431f';
const HOVERED = '#ff8c42';
const LINE = '#13264a';

//: Neighbourhood names and the City's own board labels, from the lookup the address box
//: already fetches — 5.7 KB gzipped, so reusing it costs nothing. Populated before the map
//: draws; `names.district` is keyed by number, `names.board` by `boro_cd`.
const names = { district: new Map(), board: new Map() };

//: Headline facts for the detail panel, from /data/preview.json. Null until it
//: arrives, and null forever if it does not — the panel then shows what it has.
let preview = null;

//: The district geometry's own bounds, kept so `refit` can be called again on resize.
let cityBounds = null;

//: Per-feature bounding boxes, so selecting one district frames that district instead of
//: refitting the whole city. Built once, when the geometry arrives.
const featureBounds = { council: new Map(), board: new Map() };

//: How far a framed feature is allowed to zoom. Well below MAX_ZOOM on purpose: fitting
//: one district to the frame landed around z13.5, which reads as a street map of somewhere
//: rather than as a district in its city. At 12 the surrounding districts stay in view.
const FRAME_MAX_ZOOM = 12;

//: How long a camera move takes. Animated rather than cut, so the reader can see where the
//: view went instead of being teleported.
const CAMERA_MS = 550;

//: Street level for a geocoded address, matching what the reader asked for: a located
//: point, not a dot on a city-wide map. Capped by MAX_ZOOM, which is the tile ceiling.
const ADDRESS_ZOOM = 14;

//: The MapLibre module, kept so the pin can be built after load.
let library = null;

function indexNames(lookup) {
  for (const d of lookup.districts || []) names.district.set(String(d.n), d);
  for (const b of lookup.boards || []) names.board.set(String(b.code), b);
}

//: The Council's own committees index. Per-committee pages are not linked because no source
//: this project reads carries a committee URL, and constructing nyc.gov slugs is how 59 board
//: links were once "verified" as working when they 404ed (docs/pull-requests.md).
const COMMITTEES_INDEX = 'https://council.nyc.gov/committees/';

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
    sections: (id) => {
      const hoods = (names.district.get(String(id)) || {}).hoods;
      const d = (preview && preview.districts && preview.districts[String(id)]) || {};
      const member = d.member;
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        // One value, so lines rather than a table. A seat status that is not "filled" gets
        // its own line instead of being hung off the name with a dash.
        [
          'Council Member',
          member
            ? [member.name, ...(member.seat_status === 'filled' ? [] : [`Seat recorded as ${member.seat_status}.`])]
            : ['No current member is on record for this seat.'],
        ],
        // Participatory budgeting, committees and the covering boards, exactly as the
        // district page renders them: the columns and rows are declared once, in
        // `render.district_tables`, and arrive here already shaped.
        ...(d.tables || []).map((spec) => [spec.legend, spec, spec.href]),
      ];
    },
  },
  board: {
    url: '/data/boards.geo.json',
    key: 'boro_cd',
    source: 'board',
    noun: 'community board',
    href: (id) => `/board/${id}/`,
    // The City's own label where the lookup has one ("Manhattan Community Board 1"), and the
    // derived form only as a fallback. `302` is Brooklyn's board 2: the first digit is the
    // borough, the rest the board, and the leading zero is padding, not part of the number.
    label: (id) =>
      (names.board.get(String(id)) || {}).label ||
      `Community Board ${Number(String(id).slice(1))}, ${boroughOf(id)}`,
    sections: (id) => {
      const hoods = (names.board.get(String(id)) || {}).hoods;
      const b = (preview && preview.boards && preview.boards[String(id)]) || {};
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        // Quoted as the City's dataset records it. Boards publish their own schedules and
        // the two have been observed to differ, so this is not presented as a calendar.
        ['Meets', b.cadence ? [b.cadence] : ['No City dataset records this board\'s cadence.']],
        ['Board office', [b.address, b.phone].filter(Boolean)],
        // The covering council districts and the budget register headline, from the same
        // specs the board page renders.
        ...(b.tables || []).map((spec) => [spec.legend, spec, spec.href]),
      ];
    },
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

/** Where to insert the district layers so the basemap's water paints over them.
 *
 * The shipped geometry is DCP's water-areas-included districts, which is what stops the
 * outline tracing Jamaica Bay's marsh islands — but it also means a district polygon
 * covers open water, and tinting the harbour reads as though the district owns it.
 * Inserting beneath the water fill lets the water mask exactly that part, so a district
 * reads as land without its boundary having to be a land boundary.
 *
 * Falls back to the first symbol layer, which keeps place labels above the overlay.
 */
function districtInsertionId(style) {
  const water = (style.layers || []).find(
    (layer) => layer['source-layer'] === 'water' && layer.type === 'fill'
  );
  return (water && water.id) || firstLabelLayerId(style);
}

/** The basemap style with its road layers removed, or null if it could not be had. */
async function loadBasemapStyle(url) {
  // A named style is ours already; there is nothing to fetch and no roads to strip.
  if (NAMED_STYLES[url]) return NAMED_STYLES[url];
  try {
    const style = await fetchJson(url);
    const kept = (style.layers || [])
      .filter(
        (layer) =>
          !DROPPED_SOURCE_LAYERS.has(layer['source-layer']) || KEPT_ROAD_LAYERS.has(layer.id)
      )
      .map((layer) => {
        const paint = PAINT_OVERRIDES[layer.id];
        const level = LAYER_OVERRIDES[layer.id];
        if (!paint && !level) return layer;
        return {
          ...layer,
          ...(level || {}),
          ...(paint ? { paint: { ...layer.paint, ...paint } } : {}),
        };
      });
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
    const [lib, council, board, style, lookup, facts] = await Promise.all([
      import('/vendor/maplibre-gl.mjs'),
      fetchJson(LAYERS.council.url),
      fetchJson(LAYERS.board.url),
      loadBasemapStyle(container.dataset.basemap || BASEMAP_STYLE),
      // Names and the panel's facts are both niceties: a failure in either must not cost
      // the map, which still draws, hit-tests and links through to the full page.
      fetchJson('/data/lookup.json').catch(() => null),
      fetchJson('/data/preview.json').catch(() => null),
    ]);
    MapLibre = lib;
    library = lib;
    geometry = { council, board };
    basemap = style;
    if (lookup) indexNames(lookup);
    preview = facts;
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
    maxZoom: MAX_ZOOM,
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
    // Two insertion points, because the fill and the boundary want opposite things. The
    // fill goes under the water so a water-inclusive district reads as land; the boundary
    // goes above everything, because under the roads and building footprints it came out
    // visibly broken.
    const style = basemap ? map.getStyle() : null;
    const fillBeforeId = style ? districtInsertionId(style) : undefined;
    const lineBeforeId = style ? firstLabelLayerId(style) : undefined;
    for (const name of Object.keys(LAYERS)) {
      addLayer(map, LAYERS[name], geometry[name], fillBeforeId, lineBeforeId);
    }
    // Esri ships its labels as their own tile layer, so they go on last to sit above the
    // districts. A vector style needs no equivalent: `beforeId` above does the same job.
    if (map.getSource('esri-reference') && !map.getLayer('esri-reference')) {
      map.addLayer({ id: 'esri-reference', type: 'raster', source: 'esri-reference' });
    }

    // `LAYERS`, `geometry` and `featureBounds` are all keyed by source name, so one key
    // walks all three.
    for (const name of Object.keys(LAYERS)) {
      indexBounds(LAYERS[name].source, LAYERS[name].key, geometry[name]);
    }
    cityBounds = geometryBounds(geometry.council);
    const bounds = cityBounds;
    if (bounds) {
      map.fitBounds(bounds, { padding: 24, animate: false });
      // Order matters. fitBounds first, so the zoom it lands on is "the whole city at this
      // viewport"; that becomes the floor. Then the pan box, which MapLibre re-checks against
      // the current zoom, so it has to come after.
      // The pan box is the *visible* extent at this zoom, not the geometry's bounds: those
      // are narrower than a laptop viewport, and MapLibre only constrains the centre, so the
      // leftover slack let the city be dragged up and down at full zoom out.
      //
      // Order is load-bearing and was wrong once. `setMaxBounds` re-constrains and can nudge
      // the zoom, so reading the zoom before it settles leaves a step of slack — the view
      // drifted once and then locked. Set the box, let it settle, then take the zoom that
      // results as the floor.
      map.setMaxBounds(map.getBounds());
      map.once('idle', () => {
        map.setMaxBounds(map.getBounds());
        map.setMinZoom(map.getZoom());
        lockPanAtMinZoom(map);
      });
    }

    const view = new View(map);
    view.show('council');
    bindToggle(view);
    bindClose(view);
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

function addLayer(map, layer, data, fillBeforeId, lineBeforeId) {
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
      // The resting fill is deliberately almost transparent. A district is identified by
      // its boundary, not by its tint, and at 0.45 the overlay washed the basemap out —
      // parks and water stopped reading, which was the whole reason for having a basemap.
      // Hover and selection earn the opacity instead.
      // Faded by zoom as well as by state. At street level the selected fill buried the
      // streets the reader had just searched for, so the tint is multiplied by a ramp on
      // `zoom` — never on a feature property, which is what would make it a choropleth.
      // The ordering between the three states is preserved at every zoom.
      // Faded by zoom as well as by state: at street level the selected fill buried the
      // streets the reader had just searched for.
      //
      // `['zoom']` MUST be the top-level expression, or inside a top-level `interpolate`
      // or `step`. Writing it as `['*', <state case>, <zoom interpolate>]` put zoom one
      // level down, which MapLibre rejects — and it rejects it by **discarding the whole
      // style and falling back**, so the symptom was a map with no basemap at all and
      // nothing logged (docs/OBSERVATIONS.md, 2026-10-27). So the interpolate is outside
      // and each stop carries its own state case; the ordering between the three states
      // holds at every zoom.
      'fill-opacity': [
        'interpolate',
        ['linear'],
        ['zoom'],
        12,
        [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.55,
          ['boolean', ['feature-state', 'hovered'], false],
          0.35,
          0.12,
        ],
        MAX_ZOOM,
        [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.22,
          ['boolean', ['feature-state', 'hovered'], false],
          0.16,
          0.05,
        ],
      ],
    },
  }, fillBeforeId);
  map.addLayer({
    id: `${layer.source}-line`,
    type: 'line',
    source: layer.source,
    layout: { visibility: 'none' },
    paint: { 'line-color': LINE, 'line-width': 1.1 },
  }, lineBeforeId);
}

/** Which layer is showing, and which feature in it is selected. */
class View {
  constructor(map) {
    this.map = map;
    this.name = 'council';
    this.selected = null;
    this.many = null;
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
    for (const id of this.many || []) {
      this.map.setFeatureState({ source: this.layer.source, id }, { selected: false });
    }
    this.many = null;
    hideZipOutline(this.map);
    if (this.selected !== null) {
      this.map.setFeatureState(
        { source: this.layer.source, id: this.selected },
        { selected: false }
      );
    }
    this.selected = null;

    const card = document.getElementById('map-card');
    // Only resize when the split actually collapses, or every clear costs a reflow.
    const wasSplit = document.body.classList.contains('has-selection');
    if (card) closePanel(card);
    if (wasSplit) {
      this.map.resize();
      refit(this.map);
    }
  }

  /** Several features at once, with a card that names what they have in common. */
  selectMany(ids, title) {
    this.clear();
    if (!ids.length) {
      say(`${title} does not resolve to a ${this.layer.noun} in this dataset.`);
      return;
    }
    this.many = ids;
    for (const id of ids) {
      this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    }
    const card = document.getElementById('map-card');
    const heading = document.getElementById('map-card-title');
    const body = document.getElementById('map-card-body');
    const link = document.getElementById('map-selection');
    if (!card || !heading || !body || !link) return;
    heading.textContent = title;
    // Whichever layer is showing: a ZIP resolves against both, so switching layers with a
    // ZIP on screen answers the same question about the other geography.
    const plural = `${this.layer.noun}s`;
    body.replaceChildren(
      group(`Covering this ZIP`, {
        caption: `${ids.length} ${ids.length === 1 ? this.layer.noun : plural}`,
        columns: [this.name === 'council' ? 'District' : 'Board'],
        rows: ids.map((id) => [[this.layer.label(id), this.layer.href(id)]]),
      })
    );
    link.textContent = 'Select one on the map for its details';
    link.href = this.name === 'council' ? '/district/' : '/board/';
    openPanel(card);
    this.map.resize();
    refit(this.map);
    // Frame everything highlighted, in the part of the map the panel leaves visible.
    frameBounds(this.map, unionBounds(this.layer.source, ids));
    say(`${title} covers ${ids.length} ${ids.length === 1 ? this.layer.noun : plural}, all highlighted.`);
  }

  select(id) {
    this.clear();
    this.selected = id;
    this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    this.fillCard(id);
    say(`${this.layer.label(id)} selected.`);
  }

  /** The detail panel: headline facts for whatever was selected, then a link onward. */
  fillCard(id) {
    const card = document.getElementById('map-card');
    const title = document.getElementById('map-card-title');
    const body = document.getElementById('map-card-body');
    const link = document.getElementById('map-selection');
    const asOf = document.getElementById('map-card-asof');
    if (!card || !title || !body || !link) return;

    title.textContent = this.layer.label(id);
    // Built with DOM calls and textContent, never innerHTML: these values are ours, but the
    // rule in CLAUDE.md is that nothing reaches the page as markup.
    body.replaceChildren();
    for (const [heading, rows, headingHref] of this.layer.sections(id)) {
      if (!rowCount(rows)) continue;
      body.append(group(heading, rows, headingHref));
    }
    link.textContent = `Full page for ${this.layer.label(id)}`;
    link.href = this.layer.href(id);
    if (asOf && preview && preview.as_of) {
      // Stated once for the panel rather than per field; the page carries the per-fact
      // provenance, which is what the link above is for.
      asOf.textContent = `Summary of ${this.layer.href(id)}, built ${formatAsOf(preview.as_of)}.`;
    }
    openPanel(card);
    // MapLibre does not watch its container: without this the canvas keeps the full-width
    // size and the city sits off-centre behind the panel. The floor has to be recomputed
    // too — it was the zoom that fitted the city across the *full* width, so once the panel
    // takes 25rem the city no longer fits at that zoom and pan is locked, leaving it
    // half-hidden with no way to recover.
    this.map.resize();
    refit(this.map);
    frameBounds(this.map, featureBounds[this.layer.source].get(String(id)));
  }
}

/** One board's share of a district: the figure, and a bar beneath it.
 *
 * Bars, not a stacked bar: the shares are measured per board and do not sum to 100 (44 + 29
 * + 23 for district 35), so one stacked bar would imply a complete partition it does not
 * make. One series, so no legend: the row header names each bar.
 *
 * Width is an SVG geometry attribute, not CSS: `style-src 'self'` refuses a style attribute,
 * which rules out the usual `style="width:44%"`. Square ends rather than the 4px rounded
 * ones, because `preserveAspectRatio="none"` is what lets the bar stretch to the column and
 * it would distort a corner radius.
 */
function shareCell(label, percent) {
  const cell = document.createDocumentFragment();

  const value = document.createElement('span');
  value.className = 'share-value';
  value.textContent = label;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'share-bar');
  svg.setAttribute('viewBox', '0 0 100 8');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${label} of the total`);
  for (const [cls, width] of [['share-track', 100], ['share-fill', percent]]) {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', cls);
    rect.setAttribute('x', '0');
    rect.setAttribute('y', '0');
    rect.setAttribute('width', String(width));
    rect.setAttribute('height', '8');
    svg.append(rect);
  }
  cell.append(value, svg);
  return cell;
}

/** Whether a group's content is a table spec rather than a list of lines. */
function isTable(rows) {
  return Boolean(rows) && !Array.isArray(rows) && Array.isArray(rows.columns);
}

/** How many rows a group holds, whichever shape it is. An empty group is not rendered. */
function rowCount(rows) {
  return isTable(rows) ? rows.rows.length : rows.length;
}

/** A cell's content, in the shapes `render.py` emits plus the two the panel builds itself.
 *
 * A plain string; `{text, href}` for a link; `{text, share}` for a share figure and its
 * bar; `[text, href]`; or a Node. The object forms are what travel in `preview.json`, so
 * this function and the `cell` macro in `macros.html` are the two renderers of one shape.
 */
function fillCell(target, value) {
  if (value instanceof Node) {
    target.append(value);
    return;
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    if (value.share !== undefined && value.share !== null) {
      target.append(shareCell(value.text, value.share));
      return;
    }
    fillCell(target, value.href ? [value.text, value.href] : value.text);
    return;
  }
  const [text, href] = Array.isArray(value) ? value : [value, null];
  if (!href) {
    target.textContent = text == null ? '' : String(text);
    return;
  }
  const a = document.createElement('a');
  a.textContent = text;
  a.href = href;
  if (href.startsWith('http')) {
    // Same rule as the rest of the site: an off-site link carries no referrer.
    a.rel = 'noopener noreferrer';
  }
  target.append(a);
}


/** A group's content as a real table.
 *
 * Owner's choice, 2026-10-27, over three alternatives. The panel used to put a label and
 * its value in one line separated by an em dash, which is punctuation doing structural
 * work: it reads as neither a sentence nor a list. Real `th` elements carry `scope`, so a
 * screen reader announces the column with every cell and the relationship is in the markup
 * rather than in a dash.
 */
function table(spec) {
  const element = document.createElement('table');
  element.className = 'group-table';

  if (spec.caption) {
    const caption = document.createElement('caption');
    caption.textContent = spec.caption;
    element.append(caption);
  }

  const headRow = document.createElement('tr');
  for (const name of spec.columns) {
    const th = document.createElement('th');
    th.setAttribute('scope', 'col');
    th.textContent = name;
    headRow.append(th);
  }
  const head = document.createElement('thead');
  head.append(headRow);

  const body = document.createElement('tbody');
  for (const row of spec.rows) {
    const tr = document.createElement('tr');
    row.forEach((value, index) => {
      // The first column names its row, so it is a row header and not a plain cell.
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      if (index === 0) {
        cell.setAttribute('scope', 'row');
      } else {
        // Narrow viewports hide the header row and collapse each row to a block, so the
        // column name travels with the cell for the stylesheet to print back.
        cell.dataset.label = spec.columns[index];
      }
      fillCell(cell, value);
      tr.append(cell);
    });
    body.append(tr);
  }

  element.append(head, body);
  return element;
}

/** One labelled group in the panel, as a fieldset: the era-appropriate group box.
 *
 * Content is either a list of lines — each a string, `[text, href]`, or a Node — or a table
 * spec `{ caption, columns, rows }`. Bulleted lists read as a dump; a titled group reads as
 * a record, which is what this is.
 */
function group(heading, rows, headingHref) {
  const box = document.createElement('fieldset');
  box.className = 'group';
  const legend = document.createElement('legend');
  if (headingHref) {
    const a = document.createElement('a');
    a.textContent = heading;
    a.href = headingHref;
    legend.append(a);
  } else {
    legend.textContent = heading;
  }
  box.append(legend);

  if (isTable(rows)) {
    box.append(table(rows));
    return box;
  }

  // A single value per line, for a group that is not tabular: one neighbourhood list, one
  // member, one cadence. Giving these a header row would invent columns they do not have.
  for (const row of rows) {
    const line = document.createElement('p');
    line.className = 'group-line';
    fillCell(line, row);
    box.append(line);
  }
  return box;
}

function formatAsOf(iso) {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleDateString();
}

/** The panel's close button puts the map back to full width. */
function bindClose(view) {
  const close = document.getElementById('map-card-close');
  if (!close) return;
  close.addEventListener('click', () => view.clear());
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

//: The pin dropped on a geocoded address. One marker, moved rather than recreated, so a
//: second lookup does not litter the map.
let pin = null;

function dropPin(map, MapLibre, lon, lat) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
  if (pin) {
    pin.setLngLat([lon, lat]);
    return;
  }
  // MapLibre's default marker is an inline-styled SVG, which `style-src 'self'` would
  // refuse. Ours is an element with a class, styled in site.css.
  const element = document.createElement('div');
  element.className = 'map-pin';
  element.setAttribute('aria-hidden', 'true');
  pin = new MapLibre.Marker({ element }).setLngLat([lon, lat]).addTo(map);
}

/** Fit the city to the container, then set the zoom floor and pan box from that fit.
 *
 * Called on load and again whenever the map's width changes, because every one of these
 * depends on the container: the fit, the floor derived from it, and the box derived from the
 * floor. Recomputing one without the others is what left the city behind the panel.
 */
function refit(map) {
  if (!cityBounds) return;
  map.setMinZoom(0);
  map.setMaxBounds(null);
  map.fitBounds(cityBounds, { padding: viewPadding(map), animate: false });
  map.setMaxBounds(map.getBounds());
  map.setMinZoom(map.getZoom());
  lockPanAtMinZoom(map);
}

/** Drag is off at full zoom out, and on as soon as the reader zooms in.
 *
 * `maxBounds` alone was not enough: MapLibre constrains the *centre*, and its tolerance left
 * one step of movement before pinning — the whole city slid up or down once on a laptop,
 * which is the thing being complained about. Disabling the handler is deterministic, and it
 * is honest about the state: at full zoom out the city is already entirely in frame, so there
 * is nowhere to pan to.
 */
function lockPanAtMinZoom(map) {
  const apply = () => {
    // A hair of tolerance, because zoom is a float and minZoom is whatever fitBounds left.
    if (map.getZoom() <= map.getMinZoom() + 0.01) {
      map.dragPan.disable();
    } else {
      map.dragPan.enable();
    }
  };
  map.on('zoomend', apply);
  apply();
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

    // The pin marks the address itself; the highlight marks what contains it.
    if (library) dropPin(view.map, library, detail.lon, detail.lat);

    // A ZIP covering several districts: highlight every one rather than making the reader
    // pick before they can see where any of them is.
    if (detail.zip && Array.isArray(detail.districts)) {
      const ids = view.name === 'council' ? detail.districts : detail.boards || [];
      view.selectMany(ids.map(String), `ZIP ${detail.zip}`);
      // After the selection, so a slow or missing overlay cannot delay the answer. Once
      // the outline is there the camera frames the ZIP rather than the union of whatever
      // covers it: the ZIP is what was typed, and the covering areas are listed in the
      // panel whether or not they fit in the frame.
      showZipOutline(view.map, detail.zcta || detail.zip).then((box) => {
        if (box) frameBounds(view.map, box);
      });
      return;
    }

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

/** Go to a geocoded address: street level, centred in the visible frame, pin showing.
 *
 * Zoom 12 used to leave the pin as a dot on a borough-wide view, which is not a located
 * address. `padding` is what keeps the point out from behind the panel — `easeTo` centres
 * on the container otherwise, and the panel covers the right 400 px of it.
 */
function panTo(view, detail) {
  if (!Number.isFinite(detail.lon) || !Number.isFinite(detail.lat)) return;
  view.map.easeTo({
    center: [detail.lon, detail.lat],
    zoom: Math.min(ADDRESS_ZOOM, MAX_ZOOM),
    padding: viewPadding(view.map),
    duration: CAMERA_MS,
  });
}

/** One bounding box per feature, keyed by the same property `promoteId` uses. */
function indexBounds(source, key, collection) {
  const index = featureBounds[source];
  for (const feature of (collection && collection.features) || []) {
    const id = feature.properties && feature.properties[key];
    const box = geometryBounds({ features: [feature] });
    if (id !== undefined && id !== null && box) index.set(String(id), box);
  }
}

/** The union of several features' boxes, for a ZIP that straddles districts. */
function unionBounds(source, ids) {
  const boxes = ids.map((id) => featureBounds[source].get(String(id))).filter(Boolean);
  if (!boxes.length) return null;
  return boxes.reduce((a, b) => [
    [Math.min(a[0][0], b[0][0]), Math.min(a[0][1], b[0][1])],
    [Math.max(a[1][0], b[1][0]), Math.max(a[1][1], b[1][1])],
  ]);
}

//: How long the panel takes to slide, matching the transition in site.css. The element is
//: marked `hidden` only once the close has finished, so it is never seen vanishing
//: mid-slide, and it stays out of the tab order the rest of the time.
const PANEL_SLIDE_MS = 220;

let closeTimer = null;

/** Reveal the panel, then let CSS slide it in from the edge.
 *
 * `hidden` comes off first and the class goes on in a later frame: setting both in one go
 * gives the browser no start state to animate from, so it snaps. Two nested
 * `requestAnimationFrame` calls guarantee a layout in between.
 */
function openPanel(card) {
  if (closeTimer !== null) {
    clearTimeout(closeTimer);
    closeTimer = null;
  }
  card.classList.remove('is-open');
  card.hidden = false;
  document.body.classList.add('has-selection');
  requestAnimationFrame(() => {
    requestAnimationFrame(() => card.classList.add('is-open'));
  });
}

/** Slide the panel out, and only hide it once the slide has finished. */
function closePanel(card) {
  document.body.classList.remove('has-selection');
  if (card.hidden) return;
  card.classList.remove('is-open');
  if (closeTimer !== null) clearTimeout(closeTimer);
  closeTimer = setTimeout(() => {
    card.hidden = true;
    closeTimer = null;
  }, PANEL_SLIDE_MS);
}

//: The searched ZIP's own outline. Fetched on the first ZIP lookup and never before:
//: `zips.geo.json` is 50 KB gzipped against the 145 KB the rest of the map's data costs,
//: and a reader who never types a ZIP should not pay for it. Nothing is hit-tested against
//: it — the crosswalk already answers which districts and boards a ZIP covers — so it is
//: simplified far more coarsely than the district geometry.
const ZIP_SOURCE = 'zip-outline';
const ZIP_URL = '/data/zips.geo.json';
let zipGeometry = null;
let zipPending = null;

/** Draw the dashed boundary of one modified ZCTA, or quietly draw nothing.
 *
 * The outline is a hint on top of an answer the panel has already given, so every failure
 * here is swallowed: a ZIP lookup must not break because an overlay could not be fetched.
 */
async function showZipOutline(map, zcta) {
  if (!zcta) return null;
  if (!zipGeometry) {
    if (!zipPending) zipPending = fetchJson(ZIP_URL).catch(() => null);
    zipGeometry = await zipPending;
  }
  if (!zipGeometry) return null;

  const feature = (zipGeometry.features || []).find(
    (candidate) => String((candidate.properties || {}).modzcta) === String(zcta)
  );
  if (!feature) return null;

  const data = { type: 'FeatureCollection', features: [feature] };
  if (map.getSource(ZIP_SOURCE)) {
    map.getSource(ZIP_SOURCE).setData(data);
  } else {
    map.addSource(ZIP_SOURCE, { type: 'geojson', data });
    map.addLayer({
      id: `${ZIP_SOURCE}-line`,
      type: 'line',
      source: ZIP_SOURCE,
      paint: {
        // Dashed, and a different colour from a district boundary, because it is a
        // different kind of line: the ZIP is what was asked about, not what was found.
        'line-color': '#2a2a2a',
        'line-width': 2,
        'line-dasharray': [2, 2],
      },
    });
  }
  map.setLayoutProperty(`${ZIP_SOURCE}-line`, 'visibility', 'visible');
  return geometryBounds({ features: [feature] });
}

/** Take the ZIP outline away: the next lookup is a different question. */
function hideZipOutline(map) {
  if (map.getLayer(`${ZIP_SOURCE}-line`)) {
    map.setLayoutProperty(`${ZIP_SOURCE}-line`, 'visibility', 'none');
  }
}

/** Camera padding that accounts for the detail panel.
 *
 * The panel is `position: absolute` *over* the map, so the container's width never changes
 * when it opens — measured 2026-10-27: map stays 1440 px while the panel covers the right
 * 400 px. That is why recomputing the fit on its own did nothing for the reader: MapLibre
 * centres on the container, and 400 px of that container is behind the panel. Every camera
 * move is padded by the measured overlap instead.
 */
function viewPadding(map) {
  const edge = 24;
  const flat = { top: edge, bottom: edge, left: edge, right: edge };
  const card = document.getElementById('map-card');
  if (!card || card.hidden) return flat;

  const mapBox = map.getContainer().getBoundingClientRect();
  if (!mapBox.width) return flat;

  // `offsetWidth`, not a client rect: the panel is mid-slide for 220 ms after it opens and
  // a rect includes the transform, which would make the camera padding animate along with
  // it. Docked-vs-stacked is the stylesheet's own breakpoint for the same reason — at
  // narrow widths the panel sits under the map and steals no horizontal room.
  const docked = window.matchMedia('(min-width: 52rem)').matches;
  const overlap = docked ? card.offsetWidth : 0;
  if (overlap < 40) return flat;

  // Never give away more than half the frame: past that the fit zooms out so far the city
  // is smaller than it was before the panel opened.
  return { ...flat, right: Math.min(overlap + edge, mapBox.width * 0.5) };
}

/** Frame a box in whatever part of the map the panel is not covering. */
function frameBounds(map, box) {
  if (!box) return;
  map.fitBounds(box, {
    padding: viewPadding(map),
    maxZoom: FRAME_MAX_ZOOM,
    duration: CAMERA_MS,
  });
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
