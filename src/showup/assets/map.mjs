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

//: Paint overrides applied to the basemap style after the roads come out. positron paints
//: parks `rgb(230,233,229)` on a `rgb(242,243,240)` background — a 12/255 difference, which
//: is why green space does not read on it at all. Greened here instead of switching to a
//: raster basemap, because raster labels blur on a 2x display and vector ones do not.
const PAINT_OVERRIDES = {
  park: { 'fill-color': '#d4e5ca' },
  landcover_wood: {
    'fill-color': '#c8dcbd',
    // Woods faded in between zoom 8 and 12, so they appeared only once well zoomed in.
    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.55, 10, 0.9],
  },
  landcover_glacier: { 'fill-color': '#eef2f5' },
  water: { 'fill-color': '#b6c4cc' },
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

const FILL = '#9db8d2';
const SELECTED = '#2b5f93';
const HOVERED = '#7fa0c4';
const LINE = '#31506f';

//: Neighbourhood names and the City's own board labels, from the lookup the address box
//: already fetches — 5.7 KB gzipped, so reusing it costs nothing. Populated before the map
//: draws; `names.district` is keyed by number, `names.board` by `boro_cd`.
const names = { district: new Map(), board: new Map() };

//: Headline facts for the detail panel, from /data/preview.json. Null until it
//: arrives, and null forever if it does not — the panel then shows what it has.
let preview = null;

function indexNames(lookup) {
  for (const d of lookup.districts || []) names.district.set(String(d.n), d);
  for (const b of lookup.boards || []) names.board.set(String(b.code), b);
}

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
      const meeting = preview && preview.next_meeting;
      const member = d.member;
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        [
          'Council Member',
          member
            ? [member.seat_status === 'filled' ? member.name : `${member.name} — seat ${member.seat_status}`]
            : ['No current member is on record for this seat.'],
        ],
        // Citywide, and labelled as such: Council and committee meetings belong to no
        // district, so presenting this as "this district's meeting" would be a lie.
        [
          'Next Council meeting (citywide)',
          meeting
            ? [
                meeting.committee,
                [meeting.day, meeting.start_time, meeting.mode].filter(Boolean).join(' · '),
                meeting.venue_name,
              ].filter(Boolean)
            : [],
        ],
        ['Committees', (d.committees || []).slice(0, 5).map((c) => `${c.name} — ${c.role}`)],
        [
          'Community boards here',
          (d.boards || []).map((b) => `${b.label} — ${Math.round(b.share * 100)}% of this district`),
        ],
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
      const budget = b.budget;
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        // Quoted as the City's dataset records it. Boards publish their own schedules and
        // the two have been observed to differ, so this is not presented as a calendar.
        ['Meets', b.cadence ? [b.cadence] : ['No City dataset records this board\'s cadence.']],
        ['Board office', [b.address, b.phone].filter(Boolean)],
        [
          budget
            ? `Fiscal ${budget.fiscal_year} budget requests — ${budget.total} filed`
            : 'Budget requests',
          budget
            // The register codes priority as "01"; the leading zero is padding in the
            // source, not a rank anyone wrote.
            ? budget.requests.map(
                (r) => `${r.priority ? Number(r.priority) + '. ' : ''}${r.title}`
              )
            : ['No register edition is held for this board.'],
        ],
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

/** The basemap style with its road layers removed, or null if it could not be had. */
async function loadBasemapStyle(url) {
  // A named style is ours already; there is nothing to fetch and no roads to strip.
  if (NAMED_STYLES[url]) return NAMED_STYLES[url];
  try {
    const style = await fetchJson(url);
    const kept = (style.layers || [])
      .filter((layer) => !DROPPED_SOURCE_LAYERS.has(layer['source-layer']))
      .map((layer) =>
        PAINT_OVERRIDES[layer.id]
          ? { ...layer, paint: { ...layer.paint, ...PAINT_OVERRIDES[layer.id] } }
          : layer
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
    const [library, council, board, style, lookup, facts] = await Promise.all([
      import('/vendor/maplibre-gl.mjs'),
      fetchJson(LAYERS.council.url),
      fetchJson(LAYERS.board.url),
      loadBasemapStyle(container.dataset.basemap || BASEMAP_STYLE),
      // Names and the panel's facts are both niceties: a failure in either must not cost
      // the map, which still draws, hit-tests and links through to the full page.
      fetchJson('/data/lookup.json').catch(() => null),
      fetchJson('/data/preview.json').catch(() => null),
    ]);
    MapLibre = library;
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
      // The resting fill is deliberately almost transparent. A district is identified by
      // its boundary, not by its tint, and at 0.45 the overlay washed the basemap out —
      // parks and water stopped reading, which was the whole reason for having a basemap.
      // Hover and selection earn the opacity instead.
      'fill-opacity': [
        'case',
        ['boolean', ['feature-state', 'selected'], false],
        0.55,
        ['boolean', ['feature-state', 'hovered'], false],
        0.35,
        0.12,
      ],
    },
  }, beforeId);
  map.addLayer({
    id: `${layer.source}-line`,
    type: 'line',
    source: layer.source,
    layout: { visibility: 'none' },
    paint: { 'line-color': LINE, 'line-width': 1.1 },
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
    // Only resize when the split actually collapses, or every clear costs a reflow.
    const wasSplit = document.body.classList.contains('has-selection');
    document.body.classList.remove('has-selection');
    if (wasSplit) this.map.resize();
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
    for (const [heading, rows] of this.layer.sections(id)) {
      if (!rows.length) continue;
      body.append(section(heading, rows));
    }
    link.textContent = `More details — ${this.layer.label(id)}`;
    link.href = this.layer.href(id);
    if (asOf && preview && preview.as_of) {
      // Stated once for the panel rather than per field; the page carries the per-fact
      // provenance, which is what the link above is for.
      asOf.textContent = `Summary of ${this.layer.href(id)}, built ${formatAsOf(preview.as_of)}.`;
    }
    card.hidden = false;
    document.body.classList.add('has-selection');
    // MapLibre does not watch its container: without this the canvas keeps the full-width
    // size and the city sits off-centre behind the panel.
    this.map.resize();
  }
}

/** One labelled block of lines in the panel. */
function section(heading, lines) {
  const wrap = document.createElement('section');
  const h = document.createElement('h3');
  h.textContent = heading;
  wrap.append(h);
  const ul = document.createElement('ul');
  for (const line of lines) {
    const li = document.createElement('li');
    li.textContent = line;
    ul.append(li);
  }
  wrap.append(ul);
  return wrap;
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
