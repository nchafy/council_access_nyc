// Parse the meeting table out of nyc.legistar.com/Calendar.aspx.
//
// WHY SCRAPE AT ALL
// The NYC Open Data meetings dataset (m48u-yjt8) ends in 2024, and the Legistar
// Web API now answers anonymous callers with `403 Token is required` (a key is
// free but must be requested per-person at council.nyc.gov/legislation/api/).
// Since the single most useful fact for someone trying to show up is "when is
// the next meeting", we read the public HTML calendar, which carries the current
// session including future dates.
//
// The page is an ASP.NET Telerik grid. Each row has ten cells; the ones we need:
//   0 body name, 1 meeting date, 3 meeting time, 4 location, 5 topic,
//   6 meeting-detail link, 7 agenda, 8 minutes, 9 multimedia
// Cell 2 is the per-row iCalendar export icon and cell 5 is often the
// placeholder "Multiple meeting items, please see Meeting Details...".
//
// If Legistar redesigns the grid this returns [] rather than garbage, and the
// build treats an empty result as "no live calendar" instead of failing.

import { text, href } from './html.mjs';

const ABS = (u) => {
  if (!u) return null;
  if (/^https?:/i.test(u)) return u;
  return `https://nyc.legistar.com/${String(u).replace(/^\/+/, '')}`;
};

/** Parse "12/17/2026" into an ISO date string, or null. */
export function parseUsDate(s) {
  const m = String(s || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return null;
  const [, mo, d, y] = m;
  const iso = `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  // Reject impossible dates like 02/31.
  const probe = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(probe.getTime()) || probe.getUTCDate() !== Number(d) ? null : iso;
}

export function parseCalendar(html) {
  const rows = [];
  const source = String(html);

  for (const match of source.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const cells = [...match[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map((c) => c[1]);
    if (cells.length < 7) continue;

    const date = parseUsDate(text(cells[1]));
    if (!date) continue;

    const name = text(cells[0]);
    if (!name) continue;

    const rawTime = text(cells[3]);
    const location = text(cells[4]);
    const topicCell = text(cells[5]);
    const topic = /^multiple meeting items/i.test(topicCell) ? null : topicCell || null;

    const agendaUrl = ABS(href(cells[7] ?? ''));
    const minutesUrl = ABS(href(cells[8] ?? ''));
    const mediaUrl = ABS(href(cells[9] ?? ''));

    rows.push({
      name,
      date,
      // "Deferred" appears in the time column when a meeting is postponed.
      time: /deferred|cancel/i.test(rawTime) ? null : rawTime || null,
      status: /deferred/i.test(rawTime) ? 'Deferred' : /cancel/i.test(rawTime) ? 'Cancelled' : 'Scheduled',
      location: location || null,
      topic,
      detailUrl: ABS(href(cells[6] ?? '')),
      agendaUrl,
      minutesUrl,
      mediaUrl,
    });
  }

  // Legistar can emit the same meeting twice across grouped views; de-duplicate.
  const seen = new Set();
  return rows.filter((r) => {
    const key = `${r.name}|${r.date}|${r.time}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Meetings on or after `today` (an ISO date), soonest first. */
export function upcoming(rows, today = new Date().toISOString().slice(0, 10)) {
  return rows
    .filter((r) => r.date >= today && r.status !== 'Cancelled')
    .sort((a, b) => (a.date === b.date ? String(a.time).localeCompare(String(b.time)) : a.date.localeCompare(b.date)));
}
