"""Allowlisting the URLs we inherit from scraped pages (docs/phase-1-scope.md §4.1).

Allow by listing hosts and schemes, never deny by pattern: a blocklist is a guess that
`JaVaScRiPt:` eventually defeats. Anything unrecognised returns None and the caller
renders inert text.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

__all__ = ["ALLOWED_HOSTS", "absolutize", "host_allowed", "safe_url"]

#: Hosts whose links may be rendered: government or government-vendor only.
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
        # Borough-president hosts, as nyc.gov itself lists them. Staten Island's is
        # statenislandusa.com, which is not a .gov; see BP_SITES in render.py.
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

#: The City's own WordPress network, one subdomain per board. A suffix because boards
#: migrate onto it individually, and still closed because the City controls registration
#: of `cityofnewyork.us` — unlike `brooklyncb5.org` (docs/OBSERVATIONS.md, 2026-09-29).
ALLOWED_HOST_SUFFIXES = (".cityofnewyork.us",)


def host_allowed(host: str | None) -> bool:
    """Whether a hostname may be linked: an exact allowlist entry, or a City subdomain."""
    if not host:
        return False
    host = host.lower()
    return host in ALLOWED_HOSTS or host.endswith(ALLOWED_HOST_SUFFIXES)


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

    Control characters are stripped first: `java\\nscript:alert(1)` is a live URL to a
    browser and an unknown scheme to a parser, and the two must agree before we decide.
    """
    if not href:
        return None

    candidate = "".join(ch for ch in str(href) if ch.isprintable()).strip()
    if not candidate:
        return None

    if base is not None:
        # `absolutize` cannot return None here: `candidate` is already non-empty.
        candidate = absolutize(candidate, base)

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return None

    host = parts.hostname
    if not host_allowed(host):
        return None

    # Credentials are a phishing shape, and never appear in a government link.
    if parts.username or parts.password:
        return None

    return candidate
