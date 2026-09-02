import unittest
import xml.etree.ElementTree as ET
from backend.services.alerts.gdacs import gdacs_alert_provider
from backend.schemas.alerts import GeographicScope

class TestGdacsCountryMatching(unittest.TestCase):
    """
    Regression test suite proving GDACS geographic country matching accurately resolves
    India vs non-India countries and avoids substring false positives (e.g. Indonesia -> India).
    """

    def _parse_mock_item(self, country: str, iso3: str):
        xml_template = f"""
        <item xmlns:gdacs="http://www.gdacs.org" xmlns:georss="http://www.georss.org/georss">
            <title>Test Event in {country}</title>
            <description>Test Event Description</description>
            <pubDate>Wed, 02 Sep 2026 00:00:00 GMT</pubDate>
            <gdacs:eventid>test-100</gdacs:eventid>
            <gdacs:eventtype>EQ</gdacs:eventtype>
            <gdacs:alertlevel>Green</gdacs:alertlevel>
            <gdacs:country>{country}</gdacs:country>
            <gdacs:iso3>{iso3}</gdacs:iso3>
            <georss:point>0.0 0.0</georss:point>
        </item>
        """
        elem = ET.fromstring(xml_template.strip())
        ns = {
            "gdacs": "http://www.gdacs.org",
            "georss": "http://www.georss.org/georss",
            "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
        }
        return gdacs_alert_provider._parse_single_item(elem, ns)

    def test_india_and_ind_resolves_to_india_national(self):
        alert = self._parse_mock_item("India", "IND")
        self.assertEqual(alert.scope, GeographicScope.NATIONAL)
        self.assertEqual(alert.affected_states, ["India"])

    def test_india_string_resolves_to_india_national(self):
        alert = self._parse_mock_item("India", "")
        self.assertEqual(alert.scope, GeographicScope.NATIONAL)
        self.assertEqual(alert.affected_states, ["India"])

    def test_republic_of_india_resolves_to_india_national(self):
        alert = self._parse_mock_item("Republic of India", "")
        self.assertEqual(alert.scope, GeographicScope.NATIONAL)
        self.assertEqual(alert.affected_states, ["India"])

    def test_bharat_resolves_to_india_national(self):
        alert = self._parse_mock_item("Bharat", "")
        self.assertEqual(alert.scope, GeographicScope.NATIONAL)
        self.assertEqual(alert.affected_states, ["India"])

    def test_indonesia_and_idn_is_not_india(self):
        alert = self._parse_mock_item("Indonesia", "IDN")
        self.assertNotEqual(alert.affected_states, ["India"])
        self.assertEqual(alert.affected_states, [])
        self.assertNotEqual(alert.scope, GeographicScope.NATIONAL)

    def test_finland_is_not_india(self):
        alert = self._parse_mock_item("Finland", "FIN")
        self.assertEqual(alert.affected_states, [])
        self.assertNotEqual(alert.scope, GeographicScope.NATIONAL)

    def test_argentina_is_not_india(self):
        alert = self._parse_mock_item("Argentina", "ARG")
        self.assertEqual(alert.affected_states, [])
        self.assertNotEqual(alert.scope, GeographicScope.NATIONAL)

    def test_china_is_not_india(self):
        alert = self._parse_mock_item("China", "CHN")
        self.assertEqual(alert.affected_states, [])
        self.assertNotEqual(alert.scope, GeographicScope.NATIONAL)

    def test_substring_in_countries_do_not_resolve_to_india(self):
        substring_countries = [
            ("Indonesia", "IDN"),
            ("Sint Maarten", "SXM"),
            ("Ukraine", "UKR"),
            ("Benin", "BEN"),
            ("Martinique", "MTQ"),
            ("Indo-Pacific Region", ""),
        ]
        for country, iso in substring_countries:
            with self.subTest(country=country):
                alert = self._parse_mock_item(country, iso)
                self.assertNotEqual(alert.affected_states, ["India"], f"Failed for substring country {country}")

if __name__ == "__main__":
    unittest.main()
