// Derive "when does this committee actually meet" from 25 years of meeting records.
//
// The Council publishes no standing timetable: committees are called by their
// chair, and the Legistar calendar only shows what has already been scheduled.
// So "is there a schedule?" has to be answered empirically — from the observed
// pattern of ~16,000 past meetings — and clearly labelled as a pattern rather
// than a promise.
//
// We report the modal weekday, modal start time, and modal room, plus how many
// meetings happened per year recently, so a reader can tell the difference
// between "Finance meets constantly" and "this committee met twice in 2019 and
// never again".

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/**
 * Parse Legistar's free-text time column into minutes since midnight.
 * Handles "1:30 PM", "10:00 AM", "9:30 a.m.", "12 PM", and "Deferred" (null).
 */
export function parseTime(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  if (/deferred|cancel|tbd|n\/?a/i.test(s)) return null;
  const m = s.match(/^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?/i);
  if (!m) return null;
  let hour = Number(m[1]);
  const minute = Number(m[2] || 0);
  const isPm = m[3].toLowerCase() === 'p';
  if (hour === 12) hour = isPm ? 12 : 0;
  else if (isPm) hour += 12;
  if (hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
}

export function formatTime(minutes) {
  if (minutes == null) return null;
  const h24 = Math.floor(minutes / 60);
  const m = minutes % 60;
  const suffix = h24 >= 12 ? 'PM' : 'AM';
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

/** Most common value in a list, ignoring null/undefined. Ties break by count then value. */
export function mode(values) {
  const counts = new Map();
  for (const v of values) {
    if (v == null || v === '') continue;
    counts.set(v, (counts.get(v) || 0) + 1);
  }
  if (!counts.size) return { value: null, count: 0, total: 0, share: 0 };
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  const [value, count] = [...counts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))[0];
  return { value, count, total, share: count / total };
}

const weekdayOf = (iso) => {
  // Parse as UTC so a local timezone cannot shift the date across midnight.
  const d = new Date(`${String(iso).slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : WEEKDAYS[d.getUTCDay()];
};

/**
 * @param {Array<{committee:string, date:string, timeMinutes:number|null,
 *   venueId:string, remote:boolean, hybrid:boolean, agendaStatus:string|null,
 *   minutesStatus:string|null}>} meetings
 * @param {{recentFrom?:string}} options
 */
export function committeeSchedules(meetings, { recentFrom = '2022-01-01' } = {}) {
  const groups = new Map();
  for (const m of meetings) {
    if (!m.committee) continue;
    if (!groups.has(m.committee)) groups.set(m.committee, []);
    groups.get(m.committee).push(m);
  }

  const out = [];
  for (const [committee, rows] of groups) {
    rows.sort((a, b) => a.date.localeCompare(b.date));
    const recent = rows.filter((r) => r.date >= recentFrom);
    const basis = recent.length >= 8 ? recent : rows;

    const years = new Set(basis.map((r) => r.date.slice(0, 4)));
    const day = mode(basis.map((r) => weekdayOf(r.date)));
    const time = mode(basis.map((r) => r.timeMinutes));
    const venue = mode(basis.filter((r) => !r.remote).map((r) => r.venueId));

    out.push({
      committee,
      meetings: rows.length,
      recentMeetings: recent.length,
      firstMeeting: rows[0].date,
      lastMeeting: rows[rows.length - 1].date,
      // Cadence is only meaningful if the committee is still active.
      perYearRecent: years.size ? Number((basis.length / years.size).toFixed(1)) : 0,
      typicalWeekday: day.value,
      typicalWeekdayShare: Number(day.share.toFixed(2)),
      typicalTime: formatTime(time.value),
      typicalTimeShare: Number(time.share.toFixed(2)),
      typicalVenueId: venue.value,
      typicalVenueShare: Number(venue.share.toFixed(2)),
      remoteShare: Number((basis.filter((r) => r.remote).length / (basis.length || 1)).toFixed(2)),
      // Whether you can actually read what happened, which is its own kind of
      // accessibility: an agenda tells you what will be discussed, minutes tell
      // you what was decided.
      agendaRate: Number((rows.filter((r) => /final|draft/i.test(r.agendaStatus || '')).length / rows.length).toFixed(2)),
      minutesRate: Number((rows.filter((r) => /final|draft/i.test(r.minutesStatus || '')).length / rows.length).toFixed(2)),
      basis: basis === recent ? `since ${recentFrom}` : 'all years',
    });
  }

  return out.sort((a, b) => b.recentMeetings - a.recentMeetings || b.meetings - a.meetings);
}

/**
 * Cadence of Stated Meetings — the monthly-ish sessions of the full 51-member
 * Council where bills are introduced and voted. This is the meeting a member of
 * the public most often means by "the City Council meeting".
 */
export function statedMeetingPattern(meetings, { recentFrom = '2022-01-01' } = {}) {
  const stated = meetings
    .filter((m) => /^city council$/i.test(String(m.committee || '').trim()))
    .sort((a, b) => a.date.localeCompare(b.date));
  const recent = stated.filter((r) => r.date >= recentFrom);
  const basis = recent.length >= 8 ? recent : stated;
  if (!basis.length) return null;

  const gaps = [];
  for (let i = 1; i < basis.length; i++) {
    gaps.push((Date.parse(basis[i].date) - Date.parse(basis[i - 1].date)) / 86_400_000);
  }
  gaps.sort((a, b) => a - b);
  const medianGap = gaps.length ? gaps[Math.floor(gaps.length / 2)] : null;

  const day = mode(basis.map((r) => weekdayOf(r.date)));
  const time = mode(basis.map((r) => r.timeMinutes));
  const venue = mode(basis.filter((r) => !r.remote).map((r) => r.venueId));

  return {
    meetings: stated.length,
    recentMeetings: recent.length,
    lastMeeting: basis[basis.length - 1].date,
    typicalWeekday: day.value,
    typicalTime: formatTime(time.value),
    typicalVenueId: venue.value,
    medianGapDays: medianGap == null ? null : Math.round(medianGap),
    perYearRecent: Number((basis.length / new Set(basis.map((r) => r.date.slice(0, 4))).size).toFixed(1)),
  };
}
