// Venue normalization for `meeting_location` in the City Council Meetings
// dataset (m48u-yjt8).
//
// The raw column is free text typed by clerks over 25 years. There are 30+
// distinct spellings of roughly five real places, e.g. all of these are the
// same room:
//   "Council Chambers - City Hall"
//   "Council Chambers – City Hall"      (en dash)
//   "Council Chambers  - City Hall"     (double space)
//   "HYBRID HEARING - Council Chambers - City Hall"
//
// We collapse them to canonical venues with real street addresses, and keep a
// separate `remote` / `hybrid` flag rather than treating "REMOTE HEARING" as a
// place. Anything we cannot recognize is returned as an off-site venue with its
// raw label preserved, so nothing is silently lost.

export const VENUES = {
  'city-hall-chambers': {
    id: 'city-hall-chambers',
    name: 'Council Chambers, City Hall',
    address: 'New York City Hall, City Hall Park, New York, NY 10007',
    lat: 40.712772,
    lng: -74.005974,
    entry:
      'Enter through NYPD security and metal detectors. Tell the officers which hearing you are attending. No food, beverage containers, or signs larger than 8.5" x 11" in hearing rooms.',
    note: 'Where Stated Meetings of the full 51-member Council are held.',
  },
  'city-hall-committee': {
    id: 'city-hall-committee',
    name: 'Committee Room, City Hall',
    address: 'New York City Hall, City Hall Park, New York, NY 10007',
    lat: 40.712772,
    lng: -74.005974,
    entry:
      'Enter through NYPD security and metal detectors. Tell the officers which hearing you are attending.',
    note: 'The second hearing room inside City Hall, used for committee hearings.',
  },
  '250-broadway-8': {
    id: '250-broadway-8',
    name: '250 Broadway — 8th Floor Hearing Rooms',
    address: '250 Broadway, 8th Floor, New York, NY 10007',
    lat: 40.713106,
    lng: -74.007339,
    entry:
      'Bring ID and pass through security and metal detectors. Each floor has a Sergeant-at-Arms who can direct you.',
    note: 'The current main committee-hearing location (Hearing Rooms 1, 2 and 3).',
  },
  '250-broadway-14': {
    id: '250-broadway-14',
    name: '250 Broadway — 14th Floor Committee/Hearing Room',
    address: '250 Broadway, 14th Floor, New York, NY 10007',
    lat: 40.713106,
    lng: -74.007339,
    entry: 'Bring ID and pass through security and metal detectors.',
    note: 'Heavily used for committee hearings through the 2010s and early 2020s.',
  },
  '250-broadway-16': {
    id: '250-broadway-16',
    name: '250 Broadway — 16th Floor Committee/Hearing Room',
    address: '250 Broadway, 16th Floor, New York, NY 10007',
    lat: 40.713106,
    lng: -74.007339,
    entry: 'Bring ID and pass through security and metal detectors.',
    note: 'Heavily used for committee hearings through the 2010s and early 2020s.',
  },
  emigrant: {
    id: 'emigrant',
    name: 'Emigrant Savings Bank Building',
    address: '49-51 Chambers Street, New York, NY 10007',
    lat: 40.713535,
    lng: -74.004402,
    entry: 'Bring ID and pass through building security.',
    note: 'Overflow hearing space across from City Hall.',
  },
  remote: {
    id: 'remote',
    name: 'Remote hearing (Zoom)',
    address: null,
    lat: null,
    lng: null,
    entry:
      'Remote hearings require advance sign-up through the Council’s Register to Testify form if you want to speak. Watch without signing up on the Council livestream.',
    note: 'Introduced in 2020. Remote participants are subject to the Council’s Remote Attendance Policy.',
  },
  offsite: {
    id: 'offsite',
    name: 'Off-site hearing',
    address: null,
    lat: null,
    lng: null,
    entry: 'Check the agenda PDF on Legistar for the exact address and entry instructions.',
    note:
      'Occasionally the Council holds a hearing in a borough hall, school, library, or state office building closer to affected residents.',
  },
};

/**
 * @param {string|null} raw
 * @returns {{venueId:string, remote:boolean, hybrid:boolean, rawLabel:string|null}}
 */
export function normalizeVenue(raw) {
  const rawLabel = raw == null ? null : String(raw).trim();
  if (!rawLabel) return { venueId: 'offsite', remote: false, hybrid: false, rawLabel: null };

  // Collapse dash variants and whitespace so the patterns below stay readable.
  const s = rawLabel
    .replace(/[‐-―−~]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();

  const hybrid = /hybrid/i.test(s);
  const remoteOnly = /remote|virtual|zoom|teleconference/i.test(s) && !hybrid;

  // A hybrid hearing has a physical room too, so keep matching for a venue.
  if (remoteOnly) return { venueId: 'remote', remote: true, hybrid: false, rawLabel };

  let venueId = null;
  if (/250 ?broadway/i.test(s)) {
    if (/\b8(th)?\b/.test(s)) venueId = '250-broadway-8';
    else if (/\b14(th)?\b/.test(s)) venueId = '250-broadway-14';
    else if (/\b16(th)?\b/.test(s)) venueId = '250-broadway-16';
    else venueId = '250-broadway-8';
  } else if (/emigrant|chambers street|chambers st\b/i.test(s)) {
    venueId = 'emigrant';
  } else if (/city hall/i.test(s)) {
    // "Council Committee Room - City Hall" must read as the committee room.
    venueId = /chamber/i.test(s) && !/committee/i.test(s) ? 'city-hall-chambers' : 'city-hall-committee';
  }

  if (!venueId) venueId = 'offsite';
  return { venueId, remote: false, hybrid, rawLabel };
}
