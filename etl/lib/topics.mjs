// Topic taxonomy for NYC City Council.
//
// WHY THIS EXISTS
// Four different city datasets describe "subject matter" with four different
// vocabularies:
//   - meetings (m48u-yjt8)  -> committee names, which are RENAMED every session
//     ("Committee on Transportation" became "Committee on Transportation and
//     Infrastructure"; "Committee on Women's Issues" became "Committee on Women
//     and Gender Equity")
//   - bills (6ctv-n46c)     -> committee names, same churn
//   - constituent services (b9km-gdpy) -> `complaint_type`, which happens to be
//     drawn from a near-identical list of committee-shaped labels, plus some
//     legacy ALL-CAPS truncated values from an older CRM
//   - discretionary funding (4d7f-74pe) -> `agency` (DYCD, DFTA, ...) and
//     `source` (the named funding pot, e.g. "Cultural After-School Adventure")
//
// To compare them we need one stable set of topics and an explicit, auditable
// crosswalk. RULES ARE ORDERED: the first matching rule wins, so narrower
// topics ("Higher Education", "Mental Health") must precede broader ones
// ("Education", "Health").
//
// Anything that does not match is NOT silently dropped. It lands in an
// `unmapped` bucket that the build reports and the UI discloses, so a reader
// can see how much of the picture the taxonomy fails to cover.

/** @type {Array<{id:string,label:string,blurb:string,committee?:RegExp,notCommittee?:RegExp,complaints?:string[],agencies?:string[],sources?:RegExp}>} */
export const TOPICS = [
  {
    id: 'higher-education',
    label: 'Higher Education',
    blurb: 'CUNY, community colleges, tuition and student aid.',
    committee: /higher education/i,
    complaints: [],
    agencies: ['CUNY'],
  },
  {
    id: 'mental-health',
    label: 'Mental Health & Disabilities',
    blurb: 'Mental health services, addiction, developmental disabilities.',
    committee: /mental health|disabilit|addiction|alcoholism|substance/i,
    complaints: ['MENTAL HEALTH-DISABILITY-'],
    agencies: ['DOHMH', 'DHMH'],
    sources: /Autism|Mental Health|Disabilit/i,
  },
  {
    id: 'hospitals',
    label: 'Hospitals',
    blurb: 'Public hospitals and the H+H system.',
    committee: /hospitals/i,
    complaints: ['HOSPITALS'],
    agencies: ['HHC'],
  },
  {
    id: 'health',
    label: 'Health',
    blurb: 'Public health, clinics, disease prevention, food access.',
    committee: /\bhealth\b/i,
    notCommittee: /mental|higher/i,
    complaints: ['Health', 'COVID-19'],
    sources: /HIV\/AIDS|Ending the Epidemic|Public Health/i,
  },
  {
    id: 'housing',
    label: 'Housing & Buildings',
    blurb: 'Rent, repairs, code enforcement, NYCHA, homelessness prevention.',
    committee: /housing and buildings|public housing/i,
    complaints: ['Housing and Buildings', 'HOUSING AND BUILDINGS', 'NYCHA', 'DISPLACEMENT', 'SCRIE'],
    agencies: ['HPD', 'NYCHA'],
    sources: /Housing/i,
  },
  {
    id: 'land-use',
    label: 'Land Use & Zoning',
    blurb: 'Rezonings, landmarks, dispositions of city land, new development.',
    committee: /land use|zoning|landmark|planning, disposition|public siting|waterfront|lower manhattan redevelopment/i,
    complaints: ['Land Use and Zoning', 'Land Use'],
  },
  {
    id: 'transportation',
    label: 'Transportation',
    blurb: 'Streets, buses, bike lanes, parking, for-hire vehicles.',
    committee: /transportation|for-hire vehicle/i,
    complaints: ['Transportation', 'FOR-HIRE-VEHICLES'],
    agencies: ['DOT'],
    sources: /Transportation/i,
  },
  {
    id: 'fire-emergency',
    label: 'Fire & Emergency Management',
    blurb: 'FDNY, EMS, emergency preparedness.',
    // "Fire and Criminal Justice Services" was one combined committee for
    // years; it is counted here and noted as shared with criminal justice.
    committee: /fire and (emergency|criminal)/i,
    complaints: ['FIRE AND EMERGENCY MANAGE'],
    agencies: ['FDNY', 'OEM'],
  },
  {
    id: 'criminal-justice',
    label: 'Criminal Justice',
    blurb: 'Jails, Rikers, reentry, probation, juvenile justice.',
    committee: /criminal justice|juvenile justice|justice system/i,
    complaints: ['CRIMINAL JUSTICE', 'JUSTICE SYSTEM'],
    agencies: ['MOCJ', 'OCJC', 'DOP'],
  },
  {
    id: 'public-safety',
    label: 'Public Safety',
    blurb: 'NYPD oversight, policing, community safety.',
    committee: /public safety/i,
    complaints: ['Public Safety', 'NYPD - NEW YORK POLICE DE', 'DWI'],
    agencies: ['NYPD'],
  },
  {
    id: 'education',
    label: 'Education',
    blurb: 'K-12 schools, DOE oversight, class size, school safety.',
    committee: /education/i,
    notCommittee: /higher/i,
    complaints: ['Education'],
    agencies: ['DOE'],
  },
  {
    id: 'youth',
    label: 'Youth & Children',
    blurb: 'After-school, summer jobs, foster care, child welfare.',
    committee: /youth|children/i,
    complaints: ['Youth Services'],
    agencies: ['DYCD', 'ACS'],
    sources: /Youth|CASA|Work,? Learn|Beacon/i,
  },
  {
    id: 'aging',
    label: 'Aging',
    blurb: 'Older-adult centers, home-delivered meals, senior housing.',
    committee: /aging/i,
    complaints: ['Aging'],
    agencies: ['DFTA'],
    sources: /Aging|Senior|SU-CASA/i,
  },
  {
    id: 'cultural',
    label: 'Cultural Affairs & Libraries',
    blurb: 'Museums, arts groups, the three library systems.',
    committee: /cultural affairs|librar|intergroup relation/i,
    complaints: ['Cultural Affairs'],
    agencies: ['DCLA', 'NYPL', 'NYPL-R', 'BPL', 'QBPL'],
    sources: /Cultural|Theater|Arts/i,
  },
  {
    id: 'parks',
    label: 'Parks & Recreation',
    blurb: 'Parks, playgrounds, street trees, pools.',
    committee: /parks|recreation/i,
    complaints: ['Parks'],
    agencies: ['DPR'],
    sources: /Parks|Greener|Tree/i,
  },
  {
    id: 'sanitation',
    label: 'Sanitation',
    blurb: 'Trash collection, recycling, street cleaning, rats.',
    committee: /sanitation|solid waste/i,
    complaints: ['Sanitation'],
    agencies: ['DSNY'],
    sources: /Cleanup/i,
  },
  {
    id: 'environment',
    label: 'Environment & Resiliency',
    blurb: 'Air and water quality, flooding, climate resiliency, waterfronts.',
    committee: /environmental protection|resilien/i,
    complaints: ['Environment', 'Recovery and Resiliency'],
  },
  {
    id: 'general-welfare',
    label: 'General Welfare',
    blurb: 'Cash assistance, food pantries, shelters, domestic violence services.',
    committee: /general welfare/i,
    complaints: ['General Welfare', 'Legal Services'],
    agencies: ['DSS', 'DSS/HRA', 'HRA', 'DHS'],
    sources: /Anti-Poverty|Food Pantr|DoVE|Domestic Violence|Emergency Food/i,
  },
  {
    id: 'immigration',
    label: 'Immigration',
    blurb: 'Legal services for immigrants, language access, asylum seekers.',
    committee: /immigration/i,
    complaints: ['Immigration'],
    sources: /Immigrant/i,
  },
  {
    id: 'economic-development',
    label: 'Economic Development & Small Business',
    blurb: 'Small business support, commercial corridors, job creation.',
    committee: /economic development|small business|community development/i,
    complaints: ['Economy/Jobs', 'SMALL BUSINESS'],
    agencies: ['DSBS', 'SBS'],
    sources: /Neighborhood Development|Business/i,
  },
  {
    id: 'labor',
    label: 'Civil Service & Labor',
    blurb: 'City workforce, municipal unions, worker protections.',
    committee: /civil service and labor/i,
    complaints: ['Civil Service and Labor', 'PENSION FORMS'],
  },
  {
    id: 'consumer',
    label: 'Consumer & Worker Protection',
    blurb: 'Business licensing, wage theft, paid leave, consumer complaints.',
    committee: /consumer/i,
    complaints: ['Consumer Affairs', 'Consumer Complaints'],
    agencies: ['DCA'],
  },
  {
    id: 'civil-rights',
    label: 'Civil & Human Rights',
    blurb: 'Discrimination, gender equity, human rights enforcement.',
    committee: /civil rights|civil and human rights|women|gender equity/i,
    complaints: ['Human and Civil Rights', 'CIVIL AND HUMAN RIGHTS', 'WOMEN _ GENDER EQUITY'],
  },
  {
    id: 'veterans',
    label: 'Veterans',
    blurb: 'Veterans services and benefits.',
    committee: /veteran/i,
    complaints: ['Veterans Affairs'],
  },
  {
    id: 'technology',
    label: 'Technology & Utilities',
    blurb: 'Broadband, digital access, utility oversight, city IT.',
    committee: /technology/i,
    complaints: ['Utilities'],
    agencies: ['DOITT'],
    sources: /Digital Inclusion|Broadband/i,
  },
  {
    id: 'finance',
    label: 'Finance & Budget',
    blurb: 'The city budget, taxes, property assessment, discretionary funding.',
    committee: /finance/i,
    complaints: ['Finance'],
  },
  {
    id: 'gov-ops',
    label: 'Governmental Operations',
    blurb: 'Elections, city agencies, contracts, oversight, ethics, FOIL.',
    committee: /governmental operations|rules, privileges|standards and ethics|oversight and investigations|state and federal/i,
    complaints: [
      'Governmental Operations',
      'CONTRACTS',
      'OVERSIGHT AND INVESTIGATI',
      'DOCUMENTATION',
      'JURY DUTY',
      'O AND I REQ',
      'INT REQ',
      'Government',
    ],
    agencies: ['MISC'],
    sources: /Speaker's Initiative/i,
  },
  {
    id: 'contracts',
    label: 'Contracts',
    blurb: 'City procurement and nonprofit contracting.',
    committee: /contracts/i,
  },
];

// Complaint types that describe a mood or a channel rather than a policy area.
// They are excluded from the local-demand signal instead of being forced into a
// topic they do not belong to.
export const NON_TOPIC_COMPLAINTS = new Set([
  'None',
  'Please choose an issue...',
  'Select One',
  '@getxlate.Udf_Code_Genera',
  'SPAM MAIL',
  'MEETING',
  'EVNT',
  'PATRIOTISM',
  'Quality of Life',
  'QUALITY OF LIFE',
]);

const byId = new Map(TOPICS.map((t) => [t.id, t]));
export const topicById = (id) => byId.get(id);
export const TOPIC_IDS = TOPICS.map((t) => t.id);

/** Map a committee name (any session's spelling) to a topic id, or null. */
export function topicForCommittee(name) {
  if (!name) return null;
  const s = String(name);
  // The full Council sitting as itself is not a subject-matter committee.
  if (/^city council$/i.test(s.trim())) return null;
  for (const t of TOPICS) {
    if (!t.committee) continue;
    if (t.notCommittee && t.notCommittee.test(s)) continue;
    if (t.committee.test(s)) return t.id;
  }
  return null;
}

const complaintIndex = new Map();
for (const t of TOPICS) for (const c of t.complaints || []) complaintIndex.set(c.toLowerCase(), t.id);

/** Map a constituent-services complaint_type to a topic id, or null. */
export function topicForComplaint(name) {
  if (!name) return null;
  const key = String(name).trim();
  if (NON_TOPIC_COMPLAINTS.has(key)) return null;
  const hit = complaintIndex.get(key.toLowerCase());
  if (hit) return hit;
  // Legacy CRM values are truncated to 24 chars; fall back to committee-style
  // keyword matching before giving up.
  return topicForCommittee(key);
}

const agencyIndex = new Map();
for (const t of TOPICS) for (const a of t.agencies || []) agencyIndex.set(a.toUpperCase(), t.id);

/**
 * Map a discretionary-funding award to a topic id, or null.
 * `source` (the named funding pot) is more specific than `agency`, so it wins.
 */
export function topicForFunding(source, agency) {
  if (source) {
    for (const t of TOPICS) {
      if (t.sources && t.sources.test(String(source))) return t.id;
    }
  }
  if (agency) {
    const hit = agencyIndex.get(String(agency).trim().toUpperCase());
    if (hit) return hit;
  }
  return null;
}
