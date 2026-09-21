// How to actually participate: testify, submit written testimony, get an item
// heard, and reach the people who decide.
//
// This is the one part of the site that is not derived from a dataset, because
// the answer is procedural rather than statistical. Every claim below was read
// off an official NYC Council page on 2026-09-21 and carries its source URL so
// a reader can verify it and so a future maintainer can re-check it. Nothing
// here is inferred or generalized from how other city councils work.
//
// Deliberately NOT stated: a registration cut-off time before a hearing and a
// per-speaker time limit. Both are widely assumed to exist (and chairs do
// announce time limits at the start of hearings), but council.nyc.gov/testify/
// does not publish either, so we say so rather than guess.

export const LAST_VERIFIED = '2026-09-21';

export const SOURCES = {
  testify: 'https://council.nyc.gov/testify/',
  landUse: 'https://council.nyc.gov/land-use/',
  committees: 'https://council.nyc.gov/committees/',
  legislation: 'https://council.nyc.gov/legislation/',
  remotePolicy: 'https://council.nyc.gov/procedures-governing-member-and-public-remote-attendance/',
  calendar: 'https://legistar.council.nyc.gov/Calendar.aspx',
  legistarCalendar: 'https://nyc.legistar.com/Calendar.aspx',
  visit: 'https://council.nyc.gov/visit-the-council/',
  districts: 'https://council.nyc.gov/districts/',
  api: 'https://council.nyc.gov/legislation/api/',
  data: 'https://council.nyc.gov/data/',
  billDraftingManual:
    'https://council.nyc.gov/legislation/wp-content/uploads/sites/47/2022/05/NYC-Bill-Drafting-Manual-2022.pdf',
  accessibility: 'https://council.nyc.gov/accessibility-statement/',
  foil: 'https://council.nyc.gov/foil-request/',
  livestream: 'https://council.nyc.gov/livestream/',
};

export const CONTACTS = [
  {
    id: 'hearings',
    label: 'Hearings office',
    detail: 'General questions about a hearing or about testifying',
    email: 'hearings@council.nyc.gov',
    phone: '212-482-4219',
    source: SOURCES.testify,
  },
  {
    id: 'accessibility',
    label: 'Accessibility / EEO Officer',
    detail: 'ASL, CART, or other accommodations. Request at least 3 business days before the hearing.',
    email: 'EEOOfficer@council.nyc.gov',
    phone: '212-788-6936',
    source: SOURCES.testify,
  },
  {
    id: 'interpretation',
    label: 'Language interpretation',
    detail:
      'Interpretation at a hearing. Request at least 3 business days ahead and include the hearing name and date plus your name, phone, and email.',
    email: 'translationservice@council.nyc.gov',
    phone: null,
    source: SOURCES.testify,
  },
  {
    id: 'correspondence',
    label: 'General correspondence',
    detail: 'Reaching the Council as an institution',
    email: 'correspondence@council.nyc.gov',
    phone: null,
    source: SOURCES.legislation,
  },
];

/** The four ways to put something in front of the Council, easiest first. */
export const PARTICIPATION_PATHS = [
  {
    id: 'attend',
    title: 'Show up and watch',
    effort: 'None — no sign-up',
    summary: 'All Council hearings are open to the public.',
    steps: [
      'Find a hearing on the Council calendar. Click "Meeting Details" to see the actual hearing topics — the calendar list often just says "Multiple meeting items".',
      'Go to the address on the calendar row. Enter through NYPD security and metal detectors and tell the officers which hearing you are there for.',
      'No food, beverage containers, or signs larger than 8.5" x 11" are allowed in hearing rooms.',
      'Or watch remotely on the Council livestream — no registration needed to watch.',
    ],
    sources: [SOURCES.visit, SOURCES.calendar, SOURCES.livestream],
  },
  {
    id: 'testify',
    title: 'Testify at a hearing',
    effort: 'Low — in person needs no pre-registration',
    summary:
      'Speaking at a hearing is the main formal channel for a resident to get on the record. In-person testimony needs no advance sign-up; remote testimony does.',
    steps: [
      'In person: no pre-registration required. Arrive and sign up at the hearing.',
      'Remote (Zoom Web or Zoom Phone): register in advance on the Register to Testify form. Remote participants are subject to the Council\'s Remote Attendance Policy.',
      'The form asks for your name, email, a phone number (used to verify your identity), which hearing, your subject, and whether you speak for yourself or an organization.',
      'For Zoning and Franchises or Landmarks, Public Sitings and Dispositions hearings, use the Land Use page instead of the general testify form.',
      'Need ASL, CART, or interpretation? Email the EEO Officer or translation service at least 3 business days ahead.',
    ],
    caveats: [
      'The Council does not publish a registration cut-off time or a per-speaker time limit on its testify page. Chairs commonly announce a time limit (often 2-3 minutes) at the start of a hearing. Check the agenda PDF or call the hearings office to confirm for a specific hearing.',
      'Pre-recorded testimony will not be played. You may link audio or video only if you also submit a transcript.',
    ],
    sources: [SOURCES.testify, SOURCES.landUse, SOURCES.remotePolicy],
  },
  {
    id: 'written',
    title: 'Submit written testimony',
    effort: 'Low — and you have 72 hours after the hearing',
    summary:
      'Written testimony enters the same public record as spoken testimony, and the window stays open after the hearing ends. This is the highest-leverage option if you cannot attend.',
    steps: [
      'Use the same Register to Testify form and attach your document.',
      'Accepted up to 72 hours after the hearing has been adjourned.',
      'DOC, DOCX, and PDF uploads, maximum 10 MB.',
      'Anything you submit becomes part of the permanent public record — do not include other people\'s personal details without their permission.',
    ],
    sources: [SOURCES.testify],
  },
  {
    id: 'legislate',
    title: 'Get an item onto the agenda',
    effort: 'High — requires a Council Member to carry it',
    summary:
      'There is no public petition route onto the Council agenda. Only Council Members introduce legislation, so the path runs through your member.',
    steps: [
      'Contact the Council Member for your district (or the chair of the relevant committee) and ask them to introduce it. Members work with the Council\'s Legislation Division to draft bills.',
      'Bills are formally introduced at a Stated Meeting of the full Council, then referred to a committee by subject.',
      'The committee chair decides whether and when to hold a hearing on it. That scheduling decision is where most bills stall — see the friction figures per topic.',
      'If it passes committee by majority vote it goes to the full Council, then to the Mayor, who has 30 days to sign, veto, or do nothing (it becomes law anyway).',
      'The Council publishes its Bill Drafting Manual, so you can arrive with draft language rather than an idea.',
    ],
    caveats: [
      'The Council also passes resolutions on state and federal matters, including State Legislation Resolutions (Home Rule Messages) asking Albany to act on a New York City matter.',
    ],
    sources: [SOURCES.legislation, SOURCES.billDraftingManual, SOURCES.districts],
  },
];

/** Things a reader should know about the data before trusting a number on screen. */
export const DATA_CAVEATS = [
  'No dataset published by the City records who attended or testified at a hearing, what they said, or which side they took. Nothing on this site measures public support or opposition. The "friction" figure is derived from what happened to bills, not from anyone\'s opinion.',
  'The "community groups" list is organizations that received Council discretionary funding in a district. That is a real, auditable signal of civic engagement with the Council, but it is not an attendance record, and plenty of active groups take no city money.',
  'Constituent-service records come from Council district offices and reflect what residents chose to bring to their member\'s office. They under-count issues people take elsewhere (311, a state agency, a lawyer) and depend on how diligently each office logged cases.',
  'Committees are renamed and merged every four-year session. Historical counts are grouped by subject-matter topic, not by the exact committee name of the moment, so a topic\'s totals may span several committee names.',
  'The meetings dataset ends in 2024. Upcoming meetings are scraped from the live Legistar calendar and can change or be deferred without notice — always confirm on Legistar before travelling to a hearing.',
];

export const PROCEDURES = {
  lastVerified: LAST_VERIFIED,
  sources: SOURCES,
  contacts: CONTACTS,
  paths: PARTICIPATION_PATHS,
  caveats: DATA_CAVEATS,
};
