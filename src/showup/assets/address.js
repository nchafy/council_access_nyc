// The address box. Rendered hidden and revealed here, so the dropdowns and the full
// link lists are the no-script interface rather than a fallback.
//
// The typed address is sent on submit only, never on keystroke; it never enters a URL,
// storage or a log; and anything resolvable locally never reaches the network. R33 and
// CLAUDE.md state the rule, scripts/verify.py and tests/browser/test_address_box.py
// enforce it.

(function () {
  "use strict";

  var GEOCODER = "https://geosearch.planninglabs.nyc/v2/search";

  // docs/phase-1-scope.md §6A / R40c.
  var RESOLVING_MS = 150;
  var SLOW_MS = 1200;
  var ABANDON_MS = 5000;

  var form = document.getElementById("address-form");
  var input = document.getElementById("address-input");
  var status = document.getElementById("address-status");
  var results = document.getElementById("address-results");
  var section = document.getElementById("address-section");
  var listbox = document.getElementById("address-suggest");
  if (!form || !input || !status || !results || !section || !listbox) return;

  section.hidden = false;

  var lookup = null;
  var geometry = null;
  var timers = [];

  function clearTimers() {
    timers.forEach(clearTimeout);
    timers = [];
  }

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
      "The dropdowns below list every council district and community board.";
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

  // Offer the result to the map before navigating. The map claims the event and
  // highlights instead, which is the point of having a map; with no map loaded nothing
  // listens, `defaultPrevented` stays false, and this behaves exactly as it always did.
  // The coordinate is passed when we have one, because a board cannot be derived from a
  // district number — a district overlaps two or three boards.
  function announce(district, lon, lat) {
    var event;
    var detail = { district: district, lon: lon, lat: lat };
    // Every resolution is offered to the map, including a district number, a ZIP and a
    // neighbourhood: owner's decision 2026-10-27, reversing the earlier rule that only a
    // geocoded address was. SLA-1's promise is kept because the landing page has no map, so
    // nothing claims the event there and it still navigates; on /map/ the map claims it and
    // highlights instead, which is the point of having the map.
    try {
      event = new CustomEvent("showup:located", { detail: detail, cancelable: true });
    } catch (error) {
      return false;
    }
    document.dispatchEvent(event);
    return event.defaultPrevented;
  }

  // One community board, for a suggestion picked off the list.
  function announceBoard(code) {
    var event;
    try {
      event = new CustomEvent("showup:located", {
        detail: { board: code },
        cancelable: true,
      });
    } catch (error) {
      return false;
    }
    document.dispatchEvent(event);
    return event.defaultPrevented;
  }

  // Several districts at once, for a ZIP that covers more than one.
  function announceMany(districts, zip, boards, zcta) {
    var event;
    try {
      event = new CustomEvent("showup:located", {
        detail: { districts: districts, zip: zip, boards: boards, zcta: zcta },
        cancelable: true,
      });
    } catch (error) {
      return false;
    }
    document.dispatchEvent(event);
    return event.defaultPrevented;
  }

  function go(district, lon, lat) {
    if (announce(district, lon, lat)) return;
    // Validated even though we produced it, so this can never become an open redirect.
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

  var lookupPending = null;

  function ensureLookup() {
    if (lookup) return Promise.resolve(lookup);
    // Held, not just checked: typing fires several keystrokes before the first response
    // lands, and each one was starting its own fetch of the same file.
    if (!lookupPending) {
      lookupPending = loadJSON("/data/lookup.json").then(
        function (data) {
          lookup = data;
          return data;
        },
        function (error) {
          lookupPending = null;
          throw error;
        }
      );
    }
    return lookupPending;
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

  // Even-odd ray casting, the same rule as Python's `Polygon.contains`, so the browser
  // and the build agree about which district a point is in.
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

  function resolveLocally(raw) {
    var query = raw.trim();
    if (!query) return null;

    var asNumber = query.match(/^(?:council\s+)?(?:district\s*)?#?(\d{1,2})$/i);
    if (asNumber) {
      var n = parseInt(asNumber[1], 10);
      if (n >= 1 && n <= 51) return { kind: "district", district: n };
    }

    // A ZIP straddling districts is the norm, so offer the choice rather than pick one.
    var asZip = query.match(/^(\d{5})(?:-\d{4})?$/);
    if (asZip && lookup.zips[asZip[1]]) {
      // Always "choices", even for a ZIP inside one district: the map draws the ZIP's own
      // outline, and it cannot do that if the ZIP code is dropped on the way through.
      return {
        kind: "choices",
        zip: asZip[1],
        districts: lookup.zips[asZip[1]],
        boards: (lookup.zip_boards || {})[asZip[1]] || [],
        zcta: (lookup.zip_zcta || {})[asZip[1]] || asZip[1],
      };
    }
    if (asZip) return { kind: "not_nyc", what: "ZIP code " + asZip[1] };

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
    // A name match answers only when the query has no digit, so a street address still
    // goes to the geocoder.
    if (hits.length && !/\d/.test(query)) {
      return { kind: "matches", items: hits.slice(0, 8) };
    }
    return null;
  }

  // ---- Suggestions -------------------------------------------------------------------
  //
  // Built only from `lookup.json`, which is already in the browser: 51 districts with
  // their neighbourhoods, 59 boards, 215 ZIPs. Nothing here touches the network, which is
  // what lets the submit-only promise stand (docs/phase-1-scope.md §6) while the box still
  // completes as the reader types. A street address has no local answer, so it offers no
  // suggestion and still goes to the geocoder on submit, where the best match wins.

  var SUGGESTION_LIMIT = 8;
  var open = false;
  var active = -1;
  var suggestions = [];

  function suggest(raw) {
    var query = raw.trim();
    if (!query || !lookup) return [];
    var out = [];
    var seen = {};

    function add(item) {
      if (seen[item.label] || out.length >= SUGGESTION_LIMIT) return;
      seen[item.label] = true;
      out.push(item);
    }

    var digits = query.match(/^#?(\d{1,5})$/);
    if (digits) {
      var typed = digits[1];
      // One or two digits can be a district number; five is a ZIP. Three or four is
      // neither, and says so by offering nothing rather than guessing.
      if (typed.length <= 2) {
        var n = parseInt(typed, 10);
        if (n >= 1 && n <= 51) {
          var hood = null;
          lookup.districts.forEach(function (d) {
            if (d.n === n) hood = d.hoods;
          });
          add({
            kind: "district",
            district: n,
            label: "Council District " + n + (hood ? " — " + hood : ""),
          });
        }
      }
      Object.keys(lookup.zips || {}).forEach(function (code) {
        if (code.indexOf(typed) === 0) {
          add({ kind: "zip", zip: code, label: "ZIP " + code });
        }
      });
      return out;
    }

    // A query carrying a digit anywhere else looks like a street address, which only the
    // geocoder can answer, so no local guess is offered.
    if (/\d/.test(query)) return [];

    var needle = query.toLowerCase();
    lookup.districts.forEach(function (d) {
      if (d.hoods && d.hoods.toLowerCase().indexOf(needle) !== -1) {
        add({
          kind: "district",
          district: d.n,
          label: "Council District " + d.n + " — " + d.hoods,
        });
      }
    });
    lookup.boards.forEach(function (b) {
      var haystack = (b.label + " " + (b.hoods || "")).toLowerCase();
      if (haystack.indexOf(needle) !== -1) {
        add({
          kind: "board",
          code: b.code,
          label: b.label + (b.hoods ? " — " + b.hoods : ""),
        });
      }
    });
    return out;
  }

  function closeList() {
    open = false;
    active = -1;
    suggestions = [];
    listbox.hidden = true;
    while (listbox.firstChild) listbox.removeChild(listbox.firstChild);
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function markActive() {
    var options = listbox.querySelectorAll('[role="option"]');
    for (var i = 0; i < options.length; i++) {
      var isActive = i === active;
      options[i].classList.toggle("is-active", isActive);
      options[i].setAttribute("aria-selected", isActive ? "true" : "false");
    }
    if (active >= 0 && options[active]) {
      input.setAttribute("aria-activedescendant", options[active].id);
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function openList(items) {
    closeList();
    if (!items.length) return;
    suggestions = items;
    items.forEach(function (item, index) {
      var option = document.createElement("li");
      option.id = "address-suggest-" + index;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      option.textContent = item.label;
      // `mousedown`, not `click`: the input blurs first on a click and the list is gone by
      // the time the event lands.
      option.addEventListener("mousedown", function (event) {
        event.preventDefault();
        choose(index);
      });
      listbox.appendChild(option);
    });
    open = true;
    listbox.hidden = false;
    input.setAttribute("aria-expanded", "true");
    markActive();
  }

  function choose(index) {
    var item = suggestions[index];
    if (!item) return;
    input.value = item.label.split(" — ")[0];
    closeList();
    say("");
    if (item.kind === "district") {
      go(item.district, undefined, undefined);
      return;
    }
    if (item.kind === "board") {
      // Offered to the map first, exactly like a district: on /map/ it switches to the
      // board layer and highlights. The landing page has no map, so it navigates.
      if (announceBoard(item.code)) return;
      window.location.assign("/board/" + item.code + "/");
      return;
    }
    if (item.kind === "zip") {
      var districts = (lookup.zips || {})[item.zip] || [];
      if (
        announceMany(
          districts,
          item.zip,
          (lookup.zip_boards || {})[item.zip] || [],
          (lookup.zip_zcta || {})[item.zip] || item.zip
        )
      ) {
        return;
      }
      showChoices(
        "ZIP " + item.zip + " covers " + districts.length + " council districts:",
        districts.map(function (n) {
          return { href: "/district/" + n + "/", label: "Council District " + n };
        })
      );
    }
  }

  input.addEventListener("input", function () {
    clearResults();
    if (!lookup) {
      // The index is local and small; fetching it on the first keystroke is what makes the
      // list appear without the reader having to submit first. Still our own origin only.
      ensureLookup().then(function () {
        openList(suggest(input.value));
      }, function () {});
      return;
    }
    openList(suggest(input.value));
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeList();
      return;
    }
    if (!open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      // -1 is "nothing highlighted", and the cycle runs through it, so arrowing past the
      // last row returns to the typed text rather than jumping back to the first.
      var step = event.key === "ArrowDown" ? 1 : -1;
      active += step;
      if (active >= suggestions.length) active = -1;
      if (active < -1) active = suggestions.length - 1;
      markActive();
      return;
    }
    if (event.key === "Enter") {
      // Nothing highlighted means take the best one, which is what "autocomplete" is for.
      event.preventDefault();
      choose(active >= 0 ? active : 0);
    }
  });

  input.addEventListener("blur", function () {
    // A frame of grace, so a pointer landing on an option is not undone by the blur.
    window.setTimeout(closeList, 0);
  });

  function outOfArea(feature) {
    // Checked against what the geocoder says it parsed: a Newark address still returns a
    // plausible NYC-adjacent point.
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
    // One address returns several times, for multiple entrances and for aliases, so
    // collapse on a rounded coordinate rather than on the label.
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
      // Asks NYC Planning Labs not to log the query; scripts/verify.py greps for it.
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
          // A ZIP straddling districts is the case the map answers best: highlight all of
          // them at once. The link list stays for the no-map page, and for when the map
          // does not claim the event.
          if (announceMany(local.districts, local.zip, local.boards, local.zcta)) return null;
          showChoices(
            local.districts.length === 1
              ? "ZIP " + local.zip + " is in one council district:"
              : "ZIP " + local.zip + " covers more than one council district:",
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

        timers.push(
          setTimeout(function () {
            say("Looking up…");
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

        var resolved = [];
        features.forEach(function (feature) {
          var coords = feature.geometry.coordinates;
          var district = districtAt(coords[0], coords[1]);
          if (!district) return;
          resolved.push({
            district: district,
            label: feature.properties.label || query,
            borough: feature.properties.borough || "",
            lon: coords[0],
            lat: coords[1],
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

        // The geocoder returns its candidates best first, so the best one is the answer.
        // Showing a list of them was the complaint: a reader who typed one address does not
        // want to pick it out of three, and on the map the first result is pinned and zoomed
        // like every other lookup. Where it is genuinely ambiguous — one street number in
        // three boroughs — the pin and the panel say which one was chosen, and the
        // autocomplete above the box is where a different one gets picked.
        say("");
        go(resolved[0].district, resolved[0].lon, resolved[0].lat);
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
