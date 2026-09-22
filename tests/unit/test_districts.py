"""Parsing council.nyc.gov district pages — the only source for office addresses.

The fixtures are the observed pathological cases, not the happy path. An earlier
assumption that all 51 pages were structurally identical was wrong, and these
tests exist to keep that correction from being lost.
"""

from __future__ import annotations

import pytest

from showup.sources.districts import parse_district_page, to_lines


class TestReferenceLayout:
    def test_district_1_extracts_everything(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        assert result["member_name"]
        assert result["neighborhoods"]
        assert result["committees"]
        assert result["offices"]
        assert result["email"]
        assert result["missing"] == []

    def test_district_office_has_an_address_and_phone(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        office = next(o for o in result["offices"] if o.label == "District office")
        assert office.address
        assert office.phone

    def test_committee_roles_are_captured(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        roles = {c.role for c in result["committees"]}
        # District 1's member chairs a subcommittee, so at least one non-Member
        # role must survive; a "(Chair)" line sits below the committee name.
        assert roles != {"Member"}

    def test_email_is_the_district_not_the_sitewide_footer(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        assert result["email"].lower().startswith("district")
        assert not result["email"].lower().startswith(("press@", "correspondence@"))


class TestMissingFieldsAreReportedNotGuessed:
    def test_district_3_has_no_committees(self, district_page_html):
        # Districts 3, 5, 9, 14, 25 and 26 publish no committee list.
        result = parse_district_page(3, district_page_html[3])
        assert result["committees"] == ()
        assert "committees" in result["missing"]

    @pytest.mark.parametrize("number", [35, 51])
    def test_office_hours_absent_does_not_break_the_office(self, district_page_html, number):
        # D35 and D51 omit the "Office Hours:" line. The office must still parse.
        result = parse_district_page(number, district_page_html[number])
        assert result["offices"], f"district {number} lost its offices"
        office = result["offices"][0]
        assert office.address
        assert office.hours is None or isinstance(office.hours, str)

    def test_missing_page_is_recorded_not_raised(self):
        result = parse_district_page(7, None)
        assert result["missing"] == ["page"]
        assert result["member_name"] is None

    def test_empty_page_does_not_raise(self):
        result = parse_district_page(7, "<html><body></body></html>")
        assert "member_name" in result["missing"]


class TestSafety:
    def test_no_markup_survives_into_any_field(self, district_page_html):
        for number, html in district_page_html.items():
            result = parse_district_page(number, html)
            for value in (result["member_name"], result["neighborhoods"]):
                if value:
                    assert "<" not in value, f"markup leaked into district {number}"
            for committee in result["committees"]:
                assert "<" not in committee.name

    def test_hostile_member_name_is_reduced_to_text(self):
        html = """
        <h1>District 9</h1>
        <p><script>alert('xss')</script>Jane Doe</p>
        <p>Harlem, Morningside Heights, and Hamilton Heights neighborhoods</p>
        """
        result = parse_district_page(9, html)
        assert result["member_name"] is not None
        assert "script" not in result["member_name"].lower()
        assert "alert" not in result["member_name"]

    def test_page_url_is_allowlisted(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        assert result["page_url"].startswith("https://council.nyc.gov/district-1/")


class TestToLines:
    def test_block_tags_become_line_breaks(self):
        assert to_lines("<p>One</p><p>Two</p>") == ["One", "Two"]

    def test_script_contents_never_appear(self):
        assert to_lines("<script>var x=1</script><p>Real</p>") == ["Real"]
