"""URL allowlisting. Every href on the site inherits from scraped HTML."""

from __future__ import annotations

import pytest

from showup.urls import safe_url


class TestAllowed:
    @pytest.mark.parametrize(
        "url",
        [
            "https://nyc.legistar.com/MeetingDetail.aspx?ID=1&GUID=A",
            "https://council.nyc.gov/district-35/",
            "https://legistar.council.nyc.gov/Calendar.aspx",
            "https://data.cityofnewyork.us/resource/uvw5-9znb.json",
        ],
    )
    def test_government_https_urls_pass(self, url):
        assert safe_url(url) == url


class TestRejected:
    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ],
    )
    def test_dangerous_schemes_rejected(self, url):
        assert safe_url(url) is None

    def test_control_characters_cannot_smuggle_a_scheme(self):
        # A browser ignores control characters inside a scheme, so
        # "java\nscript:" is live to a browser. Ours must not disagree with it.
        assert safe_url("java\nscript:alert(1)") is None
        assert safe_url("\x01javascript:alert(1)") is None

    def test_http_is_rejected_not_upgraded(self):
        # Silently upgrading would mean rendering a link we never verified works.
        assert safe_url("http://council.nyc.gov/") is None

    def test_unknown_host_rejected(self):
        assert safe_url("https://evil.example.com/x") is None

    def test_lookalike_host_rejected(self):
        assert safe_url("https://council.nyc.gov.evil.com/x") is None

    def test_credentials_in_url_rejected(self):
        assert safe_url("https://user:pass@council.nyc.gov/") is None

    @pytest.mark.parametrize("url", [None, "", "   "])
    def test_empty_is_none(self, url):
        assert safe_url(url) is None

    def test_protocol_relative_rejected(self):
        assert safe_url("//evil.example.com/x") is None


class TestRelativeResolution:
    def test_relative_resolves_against_base(self):
        result = safe_url("MeetingDetail.aspx?ID=1", base="https://nyc.legistar.com/")
        assert result == "https://nyc.legistar.com/MeetingDetail.aspx?ID=1"

    def test_relative_to_disallowed_base_still_rejected(self):
        assert safe_url("x.aspx", base="https://evil.example.com/") is None
