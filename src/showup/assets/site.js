// The only JavaScript on the site, and nothing essential depends on it: it makes the
// two <select>s navigate, and it compares `manifest.json`'s fetched_at against the
// reader's clock, because a build cannot know how old it will be when someone reads it
// (outline §2.12). An external file, because the CSP has no 'unsafe-inline'.

(function () {
  "use strict";

  // Each pair carries its own path shape, so a change to how the options are generated
  // cannot turn this into an open redirect.
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

  var MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  // `%-d %B %Y, %H:%M`, the same spelling the footer's build-time stamp uses.
  function stamp(milliseconds) {
    var when = new Date(milliseconds);
    function pad(value) {
      return (value < 10 ? "0" : "") + value;
    }
    return (
      when.getDate() + " " + MONTHS[when.getMonth()] + " " + when.getFullYear() +
      ", " + pad(when.getHours()) + ":" + pad(when.getMinutes())
    );
  }

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
          stale.push({ name: name, fetchedAt: fetchedAt });
        }
      });

      if (!stale.length) return;

      var notice = document.createElement("p");
      notice.className = "staleness";
      var oldest = stale.reduce(function (a, b) {
        return b.fetchedAt < a.fetchedAt ? b : a;
      });
      notice.textContent =
        "Data fetched " + stamp(oldest.fetchedAt) + " (" + oldest.name.replace(/_/g, " ") + ").";
      footer.insertBefore(notice, footer.firstChild);
    })
    .catch(function () {
      // A missing manifest is not worth a visible error: the footer states a fetch time.
    });
})();
