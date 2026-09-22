// The only JavaScript on the site, and nothing essential depends on it.
//
// Two jobs:
//   1. Make the district <select> navigate, so the dropdown works like a dropdown.
//      Without JS the same choices are plain links further down the page, and a
//      form submit lands on /district/ which lists them all.
//   2. Evaluate staleness in the browser rather than at build time. The build
//      cannot know how old it will be when someone reads it — an abandoned site
//      that still claims to be fresh is the failure this defends against
//      (outline §2.12), so `manifest.json` carries fetched_at + max_age and the
//      comparison happens here, now.
//
// Loaded as an external file because the CSP in _headers has no 'unsafe-inline'.
// No third-party code, no analytics, no network calls except the manifest.

(function () {
  "use strict";

  // 1. Dropdown navigation, for both views.
  //
  // Each pair is validated against its own path shape. Even though the option
  // values are ours, checking here means a future change to how they are
  // generated cannot turn this into an open redirect.
  [
    ["district-form", "district-select", /^\/district\/\d{1,2}\/$/],
    ["board-form", "board-select", /^\/board\/[1-5]\d{2}\/$/],
  ].forEach(function (pair) {
    var form = document.getElementById(pair[0]);
    var select = document.getElementById(pair[1]);
    var allowed = pair[2];
    if (!form || !select) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (allowed.test(select.value)) {
        window.location.assign(select.value);
      }
    });
    select.addEventListener("change", function () {
      if (select.value) {
        form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit"));
      }
    });
  });

  // 2. Staleness, computed against the reader's clock.
  var footer = document.querySelector("footer.site");
  if (!footer) return;

  fetch("/manifest.json", { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(function (manifest) {
      if (!manifest || !manifest.sources) return;

      var stale = [];
      Object.keys(manifest.sources).forEach(function (name) {
        var source = manifest.sources[name];
        var fetchedAt = Date.parse(source.fetched_at);
        if (isNaN(fetchedAt)) return;
        var ageHours = (Date.now() - fetchedAt) / 3600000;
        if (source.max_age_hours && ageHours > source.max_age_hours) {
          stale.push({ name: name, days: Math.floor(ageHours / 24) });
        }
      });

      if (!stale.length) return;

      // textContent, never innerHTML — the rule holds even for strings we
      // generated ourselves, so there is no judgement call at any call site.
      var warning = document.createElement("p");
      warning.className = "staleness";
      var worst = stale.reduce(function (a, b) {
        return b.days > a.days ? b : a;
      });
      warning.textContent =
        "This data is out of date — " +
        worst.name.replace(/_/g, " ") +
        " was last fetched " +
        worst.days +
        " day" +
        (worst.days === 1 ? "" : "s") +
        " ago. Do not rely on the meeting times below. Check nyc.legistar.com directly.";
      footer.insertBefore(warning, footer.firstChild);
    })
    .catch(function () {
      // A missing manifest is not worth a visible error: the page's own facts
      // still carry their fetch date in the footer.
    });
})();
