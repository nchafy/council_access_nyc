// The address box.
//
// Loaded only on the front page. Everything here is progressive: with JavaScript
// off the box is hidden and the two dropdowns plus the full link lists are the
// interface, which is why the no-script path is not an afterthought.
//
// PRIVACY, which drives most of the design
// The typed address is the most sensitive thing this site ever touches — it is
// where somebody lives. So:
//   - it is sent on SUBMIT ONLY. There is no autocomplete-as-you-type, which
//     removes a whole class of keystroke leakage to a third party.
//   - the request carries `private=true`, which asks NYC Planning Labs not to log
//     it. A CI grep asserts every call site includes it.
//   - it never enters a URL, the History API, a cookie, localStorage,
//     sessionStorage, or any log. The redirect target is `/district/35/`.
//   - anything resolvable locally — a district number, a ZIP, a neighbourhood or
//     board name — never reaches the network at all.
//
// WHY THE BROWSER DOES THE POINT-IN-POLYGON
// The geocoder returns a coordinate but not a council district, so the assignment
// has to happen somewhere. Doing it here keeps the address on the machine.

(function () {
  "use strict";

  var GEOCODER = "https://geosearch.planninglabs.nyc/v2/search";

  // Timings from docs/phase-1-scope.md §6A / R40c. The point of the middle state
  // is to name the slow dependency rather than leave a spinner implying we are
  // broken; the point of the last is that a spinner with no escape is a defect.
  var RESOLVING_MS = 150;
  var SLOW_MS = 1200;
  var ABANDON_MS = 5000;

  var form = document.getElementById("address-form");
  var input = document.getElementById("address-input");
  var status = document.getElementById("address-status");
  var results = document.getElementById("address-results");
  var section = document.getElementById("address-section");
  if (!form || !input || !status || !results || !section) return;

  // With JS running, reveal the box. Rendered hidden so a no-script reader is not
  // shown a control that cannot work.
  section.hidden = false;

  var lookup = null;
  var geometry = null;
  var timers = [];

  function clearTimers() {
    timers.forEach(clearTimeout);
    timers = [];
  }

  // textContent throughout — never innerHTML, per the project rule. It holds even
  // for strings we generated, so no call site needs a judgement call.
  function say(message, kind) {
    status.textContent = message || "";
    status.className = "address-status" + (kind ? " " + kind : "");
  }

  function clearResults() {
    while (results.firstChild) results.removeChild(results.firstChild);
  }

  function offerFallback() {
    var p = document.createElement("p");
    p.className = "hint";
    p.textContent =
      "You can also pick your district or board from the dropdowns below, or " +
      "browse the full lists.";
    results.appendChild(p);
  }

  function showChoices(heading, items) {
    clearResults();
    var h = document.createElement("p");
    h.className = "why";
    h.textContent = heading;
    results.appendChild(h);

    var ul = document.createElement("ul");
    ul.className = "district-list";
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.href;
      a.textContent = item.label;
      li.appendChild(a);
      ul.appendChild(li);
    });
    results.appendChild(ul);
  }

  function go(district) {
    // Validate even though we produced it: a future change to how districts are
    // derived must not be able to turn this into an open redirect.
    var target = "/district/" + district + "/";
    if (/^\/district\/([1-9]|[1-4]\d|5[01])\/$/.test(target)) {
      window.location.assign(target);
    }
  }

  var SITE_DATA_UNREACHABLE = "site-data";
  var GEOCODER_UNREACHABLE = "geocoder";

  function failure(blame, detail) {
    var error = new Error(detail);
    error.blame = blame;
    return error;
  }

  function loadJSON(url) {
    return fetch(url, { credentials: "omit" }).then(
      function (response) {
        if (!response.ok) throw failure(SITE_DATA_UNREACHABLE, url + " " + response.status);
        return response.json();
      },
      function () {
        throw failure(SITE_DATA_UNREACHABLE, url + " could not be fetched");
      }
    );
  }

  function ensureLookup() {
    if (lookup) return Promise.resolve(lookup);
    return loadJSON("/data/lookup.json").then(function (data) {
      lookup = data;
      return data;
    });
  }

  function ensureGeometry() {
    if (geometry) return Promise.resolve(geometry);
    return loadJSON("/data/districts.geo.json").then(function (data) {
      geometry = data.features.map(function (feature) {
        var rings = [];
        feature.geometry.coordinates.forEach(function (polygon) {
          polygon.forEach(function (ring) {
            rings.push(ring);
          });
        });
        var xs = [];
        var ys = [];
        rings.forEach(function (ring) {
          ring.forEach(function (point) {
            xs.push(point[0]);
            ys.push(point[1]);
          });
        });
        return {
          key: feature.properties.coundist,
          rings: rings,
          minX: Math.min.apply(null, xs),
          maxX: Math.max.apply(null, xs),
          minY: Math.min.apply(null, ys),
          maxY: Math.max.apply(null, ys),
        };
      });
      return geometry;
    });
  }

  // Ray casting with even-odd fill — the same rule as the Python `Polygon.contains`,
  // so the browser and the build agree about which district a point is in. The
  // bounding box check first is what makes 51 polygons cheap.
  function contains(shape, x, y) {
    if (x < shape.minX || x > shape.maxX || y < shape.minY || y > shape.maxY) return false;
    var inside = false;
    for (var r = 0; r < shape.rings.length; r++) {
      var ring = shape.rings[r];
      for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var xi = ring[i][0];
        var yi = ring[i][1];
        var xj = ring[j][0];
        var yj = ring[j][1];
        if (yi > y !== yj > y) {
          if (x < xi + ((y - yi) * (xj - xi)) / (yj - yi)) inside = !inside;
        }
      }
    }
    return inside;
  }

  function districtAt(lon, lat) {
    for (var i = 0; i < geometry.length; i++) {
      if (contains(geometry[i], lon, lat)) return geometry[i].key;
    }
    return null;
  }

  // ----- local resolution, no network ------------------------------------- //

  function resolveLocally(raw) {
    var query = raw.trim();
    if (!query) return null;

    // A bare district number.
    var asNumber = query.match(/^(?:council\s+)?(?:district\s*)?#?(\d{1,2})$/i);
    if (asNumber) {
      var n = parseInt(asNumber[1], 10);
      if (n >= 1 && n <= 51) return { kind: "district", district: n };
    }

    // A ZIP. Straddling districts is the norm, so this offers the choice rather
    // than picking one — a ZIP is not a district and pretending otherwise would
    // send a reader to the wrong member.
    var asZip = query.match(/^(\d{5})(?:-\d{4})?$/);
    if (asZip && lookup.zips[asZip[1]]) {
      var districts = lookup.zips[asZip[1]];
      if (districts.length === 1) return { kind: "district", district: districts[0] };
      return { kind: "choices", zip: asZip[1], districts: districts };
    }
    if (asZip) return { kind: "not_nyc", what: "ZIP code " + asZip[1] };

    // A neighbourhood or board name.
    var needle = query.toLowerCase();
    var hits = [];
    lookup.districts.forEach(function (d) {
      if (d.hoods && d.hoods.toLowerCase().indexOf(needle) !== -1) {
        hits.push({ href: "/district/" + d.n + "/", label: "Council District " + d.n + " — " + d.hoods });
      }
    });
    lookup.boards.forEach(function (b) {
      var haystack = (b.label + " " + (b.hoods || "")).toLowerCase();
      if (haystack.indexOf(needle) !== -1) {
        hits.push({ href: "/board/" + b.code + "/", label: b.label + (b.hoods ? " — " + b.hoods : "") });
      }
    });
    // Only treat a name match as an answer when the query looks like a name
    // rather than a street address, so "100 Broadway" still goes to the geocoder.
    if (hits.length && !/\d/.test(query)) {
      return { kind: "matches", items: hits.slice(0, 8) };
    }
    return null;
  }

  // ----- the geocoder ------------------------------------------------------ //

  function outOfArea(feature) {
    // Checked on what the geocoder says it PARSED, before anything renders. A
    // Newark address can still return a plausible-looking NYC-adjacent point, and
    // silently assigning it to a council district would be a confident lie.
    var parsed = feature && feature.parsed_text;
    var region = ((parsed && parsed.region) || "").toUpperCase();
    if (region && region !== "NY" && region !== "NEW YORK") return region;
    var borough = (feature && feature.borough) || "";
    var locality = (feature && feature.locality) || "";
    var known = /manhattan|brooklyn|queens|bronx|staten island|new york/i;
    if (!borough && locality && !known.test(locality)) return locality;
    return null;
  }

  function dedupe(features) {
    // The same address often comes back several times (a building with multiple
    // entrances, or an alias like "100 B'WAY"). Deduping on a rounded coordinate
    // collapses those without needing to compare label strings.
    var seen = {};
    var out = [];
    features.forEach(function (feature) {
      var coords = feature.geometry && feature.geometry.coordinates;
      if (!coords) return;
      var key = coords[0].toFixed(5) + "," + coords[1].toFixed(5);
      if (seen[key]) return;
      seen[key] = true;
      out.push(feature);
    });
    return out;
  }

  function search(query) {
    var url =
      GEOCODER +
      "?text=" +
      encodeURIComponent(query) +
      "&size=8" +
      // private=true asks NYC Planning Labs not to log the query. Every call site
      // must carry it; scripts/verify.py greps for exactly this.
      "&private=true";
    return fetch(url, { credentials: "omit", referrerPolicy: "no-referrer" }).then(
      function (response) {
        if (!response.ok) throw failure(GEOCODER_UNREACHABLE, "geocoder " + response.status);
        return response.json();
      },
      function () {
        throw failure(GEOCODER_UNREACHABLE, "geocoder unreachable");
      }
    );
  }

  // ----- submit ------------------------------------------------------------ //

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearTimers();
    clearResults();

    var query = input.value.trim();
    if (!query) {
      say("Type an address, a ZIP code, a neighbourhood, or a district number.", "warn");
      return;
    }

    say("Looking up…");

    ensureLookup()
      .then(function () {
        var local = resolveLocally(query);

        if (local && local.kind === "district") {
          say("");
          go(local.district);
          return null;
        }
        if (local && local.kind === "choices") {
          say("");
          showChoices(
            "ZIP " + local.zip + " covers more than one council district. Pick yours:",
            local.districts.map(function (n) {
              return { href: "/district/" + n + "/", label: "Council District " + n };
            })
          );
          return null;
        }
        if (local && local.kind === "matches") {
          say("");
          showChoices("Matches for “" + query + "”:", local.items);
          return null;
        }
        if (local && local.kind === "not_nyc") {
          say(
            "That " + local.what + " is not in New York City. This site only covers the five boroughs.",
            "warn"
          );
          offerFallback();
          return null;
        }

        // Nothing local matched, so this needs the geocoder and the geometry.
        timers.push(
          setTimeout(function () {
            say("Looking up your address…");
          }, RESOLVING_MS)
        );
        timers.push(
          setTimeout(function () {
            say(
              "Still looking up — the City's address lookup (geosearch.planninglabs.nyc) " +
                "is slow right now.",
              "warn"
            );
          }, SLOW_MS)
        );
        timers.push(
          setTimeout(function () {
            clearTimers();
            say(
              "Giving up on the City's address lookup — it did not answer in 5 seconds.",
              "warn"
            );
            offerFallback();
          }, ABANDON_MS)
        );

        return Promise.all([search(query), ensureGeometry()]);
      })
      .then(function (pair) {
        if (!pair) return;
        clearTimers();

        var features = dedupe((pair[0] && pair[0].features) || []);
        if (!features.length) {
          say("No match for “" + query + "”. Check the spelling, or add the borough.", "warn");
          offerFallback();
          return;
        }

        var foreign = outOfArea(features[0].properties);
        if (foreign) {
          say(
            "That looks like " + foreign + ", which is outside New York City. " +
              "This site only covers the five boroughs.",
            "warn"
          );
          offerFallback();
          return;
        }

        // Resolve each candidate to a district, then decide.
        var resolved = [];
        features.forEach(function (feature) {
          var coords = feature.geometry.coordinates;
          var district = districtAt(coords[0], coords[1]);
          if (!district) return;
          resolved.push({
            district: district,
            label: feature.properties.label || query,
            borough: feature.properties.borough || "",
          });
        });

        if (!resolved.length) {
          say(
            "We found that address but could not place it in a council district. " +
              "It may be just outside the city boundary.",
            "warn"
          );
          offerFallback();
          return;
        }

        var distinct = {};
        resolved.forEach(function (item) {
          distinct[item.district] = true;
        });

        if (Object.keys(distinct).length === 1) {
          say("");
          go(resolved[0].district);
          return;
        }

        // Genuinely ambiguous — "100 Broadway" exists in three boroughs. Ask,
        // borough first, because that is how a New Yorker disambiguates.
        say("");
        showChoices(
          "More than one place matches “" + query + "”. Which did you mean?",
          resolved.map(function (item) {
            return {
              href: "/district/" + item.district + "/",
              label:
                item.label +
                (item.borough ? " (" + item.borough + ")" : "") +
                " — Council District " + item.district,
            };
          })
        );
      })
      .catch(function (error) {
        clearTimers();
        say(
          error && error.blame === SITE_DATA_UNREACHABLE
            ? "This page could not load its own lookup data, so the address box is not " +
                "working. That is a fault here, not with the City. Use the dropdowns below."
            : "The City's address lookup did not respond. Nothing was saved — try again, " +
                "or use the dropdowns below.",
          "warn"
        );
        offerFallback();
      });
  });
})();
