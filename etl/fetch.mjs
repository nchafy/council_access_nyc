// Stage 1 of the ETL: pull every upstream source to disk, unmodified.
//
// Fetching and transforming are deliberately separate stages. The raw cache in
// etl/raw/ means you can iterate on the (frequently changing) transform logic in
// build.mjs without re-downloading ~130k rows and 51 HTML pages every time, and
// it gives you something to diff when a city dataset changes shape underneath
// you.
//
// Usage:
//   node etl/fetch.mjs          # skip anything already cached
//   node etl/fetch.mjs --force  # re-download everything

import { mkdir, writeFile, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const RAW = join(HERE, 'raw');
const FORCE = process.argv.includes('--force');

const UA = 'nyc-council-access/0.1 (civic data ETL; contact: local run)';
const SOCRATA = 'https://data.cityofnewyork.us';

// NYC Open Data throttles anonymous callers. An app token raises the limit a
// lot; set one if you have it, but everything here works without one.
const APP_TOKEN = process.env.SOCRATA_APP_TOKEN || '';

const log = (...a) => console.log('[fetch]', ...a);

async function exists(p) {
  try {
    const s = await stat(p);
    return s.size > 0;
  } catch {
    return false;
  }
}

async function getText(url, { tries = 5, label = url } = {}) {
  let lastErr;
  for (let attempt = 1; attempt <= tries; attempt++) {
    try {
      const headers = { 'User-Agent': UA, Accept: 'application/json,text/html,*/*' };
      if (APP_TOKEN && url.startsWith(SOCRATA)) headers['X-App-Token'] = APP_TOKEN;
      const res = await fetch(url, { headers, signal: AbortSignal.timeout(120_000) });
      if (res.status === 429 || res.status >= 500) {
        throw new Error(`HTTP ${res.status}`);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status} (not retryable)`);
      return await res.text();
    } catch (err) {
      lastErr = err;
      if (String(err.message).includes('not retryable')) break;
      const backoff = Math.min(30_000, 1000 * 2 ** (attempt - 1));
      log(`retry ${attempt}/${tries} for ${label}: ${err.message} (waiting ${backoff}ms)`);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  throw new Error(`failed to fetch ${label}: ${lastErr?.message}`);
}

const getJSON = async (url, opts) => JSON.parse(await getText(url, opts));

/**
 * Page through a Socrata resource. `select` keeps the payload lean: we only ask
 * for columns the build actually consumes.
 */
async function socrataAll(id, { select, where, order, pageSize = 50_000, label }) {
  const rows = [];
  for (let offset = 0; ; offset += pageSize) {
    const qs = new URLSearchParams();
    if (select) qs.set('$select', select);
    if (where) qs.set('$where', where);
    // A stable sort is required for correct paging; Socrata does not guarantee
    // order otherwise and you can silently get duplicate or missing rows.
    qs.set('$order', order || ':id');
    qs.set('$limit', String(pageSize));
    qs.set('$offset', String(offset));
    const url = `${SOCRATA}/resource/${id}.json?${qs}`;
    const page = await getJSON(url, { label: `${label || id} offset=${offset}` });
    rows.push(...page);
    log(`  ${label || id}: ${rows.length} rows`);
    if (page.length < pageSize) break;
  }
  return rows;
}

async function save(name, data) {
  const p = join(RAW, name);
  const body = typeof data === 'string' ? data : JSON.stringify(data);
  await writeFile(p, body);
  log(`wrote ${name} (${(body.length / 1e6).toFixed(2)} MB)`);
}

/** Run a task unless its output is already cached. */
async function step(name, fn) {
  const p = join(RAW, name);
  if (!FORCE && (await exists(p))) {
    log(`skip ${name} (cached; use --force to refresh)`);
    return;
  }
  await save(name, await fn());
}

// ---------------------------------------------------------------------------

async function main() {
  await mkdir(RAW, { recursive: true });

  // 1. Meetings, 1999-2024. The "where do meetings happen / is there a
  //    schedule" backbone.
  await step('meetings.json', () =>
    socrataAll('m48u-yjt8', {
      select:
        'event_id,committee,meeting_date,meeting_time,meeting_location,note,agenda_status,minutes_status,url',
      label: 'meetings',
    }),
  );

  // 2. Bills and local laws, 1998-2024. Topics, sponsors, and the status field
  //    that lets us measure whether hearings turn into law.
  await step('bills.json', () =>
    socrataAll('6ctv-n46c', {
      select:
        'matter_id,status,file_num,law_number,primary_sponsor,committee,intro_date,passed_date,enacted_date,previous_file_number,title,summary',
      label: 'bills',
    }),
  );

  // 3. Discretionary funding awards. Our best structured proxy for "which
  //    community organizations are actually engaged with the Council", because
  //    it is per-district, per-year, names the org, and includes an EIN.
  await step('funding.json', () =>
    socrataAll('4d7f-74pe', {
      select:
        'fiscal_year,source,council_member,legal_name_of_organization,ein,status,amount,agency,program_name,address,city,postcode,borough,latitude,longitude,community_board,council_district,purpose_of_funds,fiscal_conduit_name',
      label: 'funding',
    }),
  );

  // 4. Constituent service issues, aggregated server-side. 341k raw rows would
  //    be pointless to ship; the district x topic x year counts are the signal.
  await step('constituent.json', () =>
    getJSON(
      `${SOCRATA}/resource/b9km-gdpy.json?` +
        new URLSearchParams({
          $select:
            'council_dist,complaint_type,date_trunc_y(opendate) as yr,count(1) as n',
          $group: 'council_dist,complaint_type,date_trunc_y(opendate)',
          $limit: '200000',
        }),
      { label: 'constituent (grouped)' },
    ),
  );

  // 5. Committee membership, and 6. members. Joined to answer "which hearings
  //    does MY member sit on".
  await step('committee_membership.json', () =>
    socrataAll('aabe-yfm9', {
      select:
        'member_id,full_name,first_name,last_name,committee,appointment_type,start_date,end_date,committee_id',
      label: 'committee membership',
    }),
  );

  await step('members.json', () =>
    socrataAll('uvw5-9znb', {
      select: 'name,council_member_id,term_start,term_end,district,office_id',
      label: 'members',
    }),
  );

  // 7. District boundaries (water areas included, so coastal addresses resolve).
  await step('districts.geojson', () =>
    getText(
      `${SOCRATA}/api/geospatial/872g-cjhh?method=export&format=GeoJSON`,
      { label: 'district geojson' },
    ),
  );

  // 8. Live calendar from Legistar. The open dataset stops at 2024; this page
  //    carries the current session including future meetings, which is what a
  //    user actually needs ("when is the next one").
  await step('legistar_calendar.html', () =>
    getText('https://nyc.legistar.com/Calendar.aspx', { label: 'legistar calendar' }),
  );

  // 9. The 51 district pages on council.nyc.gov: member name, neighborhoods,
  //    committee list, district office address, phone, email. There is no open
  //    dataset with district office addresses, so this is the only source.
  await step('district_pages.json', async () => {
    const out = {};
    // Serial with a small delay: this is a WordPress site, not an API, and 51
    // polite requests take well under a minute.
    for (let d = 1; d <= 51; d++) {
      try {
        out[d] = await getText(`https://council.nyc.gov/district-${d}/`, {
          label: `district-${d}`,
          tries: 3,
        });
        log(`  district-${d} ok`);
      } catch (err) {
        log(`  district-${d} FAILED: ${err.message}`);
        out[d] = null;
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    return out;
  });

  log('done.');
}

main().catch((err) => {
  console.error('[fetch] fatal:', err);
  process.exit(1);
});
