"""Allowlisting the URLs we inherit from scraped pages.

Every outbound link on this site comes from somebody else's HTML: a Legistar
agenda PDF, a meeting-detail page, a council.nyc.gov member page. A link is a
place an attacker can put `javascript:` or a `data:` document, so upstream URLs
are checked against an explicit host and scheme allowlist before they are allowed
to become an `href` (docs/phase-1-scope.md §4.1).

The policy is allow-by-listing, never deny-by-pattern: a blocklist of dangerous
schemes is a guess about what is dangerous, and `\\x01javascript:` or
`JaVaScRiPt:` eventually defeats it. Anything unrecognised returns None and the
caller renders inert text instead of a link — a missing link is a small product
failure, a live hostile link is a security one.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

__all__ = ["ALLOWED_HOSTS", "absolutize", "safe_url"]

#: Hosts whose links may be rendered. Every entry is a government or
#: government-vendor host this project already reads data from.
ALLOWED_HOSTS = frozenset(
    {
        "nyc.legistar.com",
        "legistar.council.nyc.gov",
        "council.nyc.gov",
        "data.cityofnewyork.us",
        "www.nyc.gov",
        "nyc.gov",
        "geosearch.planninglabs.nyc",
        "cb.nyc.gov",
        # Borough presidents appoint community board members and their offices
        # process the applications, so the board view links them. These are the
        # hosts nyc.gov itself publishes. Note two quirks found while verifying:
        # the Bronx deep link nyc.gov publishes (/community-boards/) is a 404, so
        # only roots are linked; and Staten Island's borough president site is on
        # statenislandusa.com, which is not a .gov but is what nyc.gov lists.
        "bronxboropres.nyc.gov",
        "www.brooklynbp.nyc.gov",
        "brooklynbp.nyc.gov",
        "www.manhattanbp.nyc.gov",
        "manhattanbp.nyc.gov",
        "www.queensbp.nyc.gov",
        "queensbp.nyc.gov",
        "www.statenislandusa.com",
        "statenislandusa.com",
        "communityprofiles.planning.nyc.gov",
    }
)

_ALLOWED_SCHEMES = frozenset({"https"})


def absolutize(href: str | None, base: str) -> str | None:
    """Resolve a possibly-relative upstream href against its source page."""
    if not href:
        return None
    candidate = str(href).strip()
    if not candidate:
        return None
    return urljoin(base, candidate)


def safe_url(href: str | None, *, base: str | None = None) -> str | None:
    """Return `href` if it is a permitted absolute https URL, else None.

    Control characters are stripped before parsing because browsers ignore them
    inside a scheme: `java\\nscript:alert(1)` is a live URL to a browser and an
    unknown scheme to a naive parser, so the two must agree before we decide.
    """
    if not href:
        return None

    candidate = "".join(ch for ch in str(href) if ch.isprintable()).strip()
    if not candidate:
        return None

    if base is not None:
        # `absolutize` cannot return None here: `candidate` is already non-empty and
        # stripped, which is the only case that makes it give up. No None guard.
        candidate = absolutize(candidate, base)

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return None

    host = parts.hostname
    if host is None or host.lower() not in ALLOWED_HOSTS:
        return None

    # Credentials in a URL (https://user:pass@host/) are a phishing shape and
    # never appear in legitimate government links.
    if parts.username or parts.password:
        return None

    return candidate
