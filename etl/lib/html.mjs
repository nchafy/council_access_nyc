// Minimal HTML entity decoding.
//
// Node has no built-in entity decoder and the two pages we scrape
// (council.nyc.gov, nyc.legistar.com) only use a handful of entities plus
// numeric escapes. That is a small enough surface to handle directly rather
// than take a dependency for it.

const NAMED = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
  ndash: '–',
  mdash: '—',
  lsquo: '‘',
  rsquo: '’',
  ldquo: '“',
  rdquo: '”',
  hellip: '…',
  amp039: "'",
  '#39': "'",
};

export function decode(input) {
  return String(input).replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g, (match, body) => {
    if (body[0] === '#') {
      const hex = body[1] === 'x' || body[1] === 'X';
      const code = parseInt(hex ? body.slice(2) : body.slice(1), hex ? 16 : 10);
      return Number.isFinite(code) && code > 0 ? String.fromCodePoint(code) : match;
    }
    const hit = NAMED[body.toLowerCase()];
    return hit === undefined ? match : hit;
  });
}

/** Strip tags from an HTML fragment and collapse whitespace. */
export function text(fragment) {
  return decode(String(fragment).replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    .trim();
}

/** Extract the href from an anchor inside a fragment, if any. */
export function href(fragment) {
  const m = String(fragment).match(/href\s*=\s*["']([^"']+)["']/i);
  return m ? decode(m[1]) : null;
}
