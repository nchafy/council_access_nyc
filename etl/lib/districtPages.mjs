// Parse council.nyc.gov/district-N/ pages.
//
// There is no open dataset with district office addresses, phone numbers, or
// current committee assignments, so these 51 WordPress pages are the only
// source. We flatten the HTML to visible text lines and read the page by its
// visual structure, which has been stable and is identical across all 51 pages:
//
//   District 1
//   Christopher Marte
//   The Lower East Side, Chinatown, ...        <- neighborhoods
//   ...biography paragraphs...
//   Committees
//   Committee on Public Housing
//   ...
//   Subcommittee on Landmarks, ...
//   (Chair)                                    <- role attaches to line above
//   Caucuses
//   ...
//   District Office
//   65 East Broadway
//   New York, NY 10002
//   Phone: 212-587-3159
//   Fax: 212-587-3138
//   Office Hours: 10:00 a.m. to 6:00 p.m.
//   Legislative Office
//   250 Broadway, Suite 1749
//   New York, NY 10007
//   ...
//   District1@council.nyc.gov
//
// Tag-soup parsing is fragile by nature, so every field is optional and
// `parseDistrictPage` reports what it could not find rather than throwing. The
// build surfaces those gaps instead of shipping silent blanks.

import { decode } from './html.mjs';

/** Flatten HTML to an array of non-empty visible text lines. */
export function toLines(html) {
  const withoutScripts = String(html)
    .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ');
  return decode(withoutScripts.replace(/<[^>]+>/g, '\n'))
    .split('\n')
    .map((l) => l.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
}

const ROLE_LINE = /^\((Chair|Co-Chair|Vice Chair|Chairperson)\)$/i;
const COMMITTEE_LINE = /^(Committee on |Subcommittee on |Select Committee)/i;
const SECTION_END = /^(Caucuses|Biography|Staff Directory|Community Events|Letters from|District Office|FY\d{4} Budget|Subscribe|Media Inquiries|Adopt a Tree)/i;

/**
 * Pull the committee list. The word "Committees" also appears twice in the site
 * navigation, so we anchor on the occurrence that is actually followed by a
 * committee name.
 */
function parseCommittees(lines) {
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^Committees$/i.test(lines[i]) && lines[i + 1] && COMMITTEE_LINE.test(lines[i + 1])) {
      start = i + 1;
      break;
    }
  }
  if (start === -1) return [];

  const out = [];
  for (let i = start; i < lines.length; i++) {
    const line = lines[i];
    if (SECTION_END.test(line)) break;
    if (ROLE_LINE.test(line)) {
      if (out.length) out[out.length - 1].role = line.replace(/[()]/g, '');
      continue;
    }
    if (COMMITTEE_LINE.test(line)) out.push({ name: line, role: 'Member' });
  }
  return out;
}

const PHONE = /^Phone:\s*(.+)$/i;
const FAX = /^Fax:\s*(.+)$/i;
const HOURS = /^Office Hours:\s*(.+)$/i;
const ZIP_LINE = /,\s*(NY|New York)\s*,?\s*\d{5}/i;

/**
 * Read one office block: the lines after a heading like "District Office" up to
 * the next heading. Address lines are whatever comes before the first
 * Phone/Fax/Hours line.
 */
function parseOffice(lines, headingIndex) {
  if (headingIndex === -1) return null;
  const office = { address: null, phone: null, fax: null, hours: null };
  const addressLines = [];
  for (let i = headingIndex + 1; i < Math.min(headingIndex + 12, lines.length); i++) {
    const line = lines[i];
    if (/^(District Office|Legislative Office|Visit the Council|Send Email)$/i.test(line)) break;
    const phone = line.match(PHONE);
    if (phone) {
      office.phone = phone[1].trim();
      continue;
    }
    const fax = line.match(FAX);
    if (fax) {
      office.fax = fax[1].trim();
      continue;
    }
    const hours = line.match(HOURS);
    if (hours) {
      office.hours = hours[1].trim();
      continue;
    }
    if (!office.phone && !office.fax) addressLines.push(line);
    // Stop collecting address once we've seen the city/state/zip line.
    if (ZIP_LINE.test(line)) {
      const next = lines[i + 1] || '';
      if (!PHONE.test(next) && !FAX.test(next) && !HOURS.test(next)) break;
    }
  }
  if (addressLines.length) office.address = addressLines.join(', ');
  return office.address || office.phone ? office : null;
}

const findHeading = (lines, re) => lines.findIndex((l) => re.test(l));

/**
 * @param {number} district
 * @param {string|null} html
 * @returns {{district:number, member:string|null, neighborhoods:string|null,
 *   committees:Array<{name:string,role:string}>, districtOffice:object|null,
 *   legislativeOffice:object|null, email:string|null, url:string,
 *   missing:string[]}}
 */
export function parseDistrictPage(district, html) {
  const url = `https://council.nyc.gov/district-${district}/`;
  const result = {
    district,
    member: null,
    neighborhoods: null,
    committees: [],
    districtOffice: null,
    legislativeOffice: null,
    email: null,
    url,
    missing: [],
  };
  if (!html) {
    result.missing.push('page');
    return result;
  }

  const lines = toLines(html);

  // The "District N" heading is followed by the member's name, then the
  // neighborhood list.
  const headingIndex = lines.findIndex((l) => new RegExp(`^District ${district}$`).test(l));
  if (headingIndex !== -1) {
    const name = lines[headingIndex + 1];
    // Guard against pages where the heading is the last thing (vacant seat).
    if (name && !/^District /i.test(name) && name.length < 60) result.member = name;
    const hood = lines[headingIndex + 2];
    if (hood && hood.length > 15 && !/^Council Member/i.test(hood)) result.neighborhoods = hood;
  }

  result.committees = parseCommittees(lines);
  result.districtOffice = parseOffice(lines, findHeading(lines, /^District Office$/i));
  result.legislativeOffice = parseOffice(lines, findHeading(lines, /^Legislative Office$/i));

  const email = html.match(/District\s*\d+@council\.nyc\.gov/i) || html.match(/[A-Za-z0-9._%+-]+@council\.nyc\.gov/);
  // press@ and correspondence@ are in the site footer on every page; they are
  // not the district's own address.
  if (email && !/^(press|correspondence|EEOOfficer|translationservice|hearings)@/i.test(email[0])) {
    result.email = email[0];
  }

  for (const [key, value] of Object.entries({
    member: result.member,
    neighborhoods: result.neighborhoods,
    committees: result.committees.length || null,
    districtOffice: result.districtOffice,
    email: result.email,
  })) {
    if (!value) result.missing.push(key);
  }

  return result;
}
