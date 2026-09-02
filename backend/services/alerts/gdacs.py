import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError
from backend.services.alerts.base import BaseAlertProvider
from backend.schemas.alerts import (
    DisasterAlert,
    AlertSeverity,
    AlertUrgency,
    AlertCertainty,
    AlertStatus,
    AlertSource,
    GeographicScope,
)

GDACS_FEED_URL = "https://www.gdacs.org/xml/rss.xml"

INDIA_EXACT_COUNTRIES = {
    "india", "republic of india", "bharat"
}

GDACS_EVENT_TYPES: Dict[str, str] = {
    "TC": "Tropical Cyclone",
    "EQ": "Earthquake",
    "FL": "Flood",
    "VO": "Volcano",
    "DR": "Drought",
    "WF": "Wildfire",
    "TS": "Tsunami",
    "EP": "Epidemic",
    "IN": "Insect Infestation",
}

GDACS_SEVERITY_MAP: Dict[str, AlertSeverity] = {
    "red": AlertSeverity.EXTREME,
    "orange": AlertSeverity.SEVERE,
    "green": AlertSeverity.MODERATE,
}


class GdacsAlertProvider(BaseAlertProvider):
    """
    GDACS (Global Disaster Alert and Coordination System) Alert Provider.
    Fetches live GDACS public RSS feed, normalizes events to internal DisasterAlert schema,
    deduplicates by stable GDACS episode ID, and ranks India-relevant events.
    """

    def __init__(
        self,
        feed_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.feed_url = feed_url or GDACS_FEED_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    async def fetch_active_alerts(self, force_refresh: bool = False) -> List[DisasterAlert]:
        """
        Fetches, parses, deduplicates, and caches GDACS disaster alerts.
        """
        cache_key = "gdacs:alerts:all"
        if not force_refresh:
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                logger.debug("[Cache HIT] GDACS disaster alerts")
                return [DisasterAlert(**item) for item in cached_data]

        try:
            client = await http_client_manager.get_client()
            response = await client.get(self.feed_url, timeout=self.timeout)
        except httpx.TimeoutException:
            logger.error(f"[Upstream timeout] GDACS feed at {self.feed_url}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning("[Cache STALE FALLBACK] Serving recent GDACS alerts within window")
                return [DisasterAlert(**item) for item in val]
            raise UpstreamTimeoutError(provider="GDACS Feed", timeout_seconds=self.timeout)
        except Exception as e:
            logger.error(f"[Network error] GDACS: {str(e)}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                return [DisasterAlert(**item) for item in val]
            raise UpstreamProviderError(provider="GDACS Feed", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"[Upstream {response.status_code}] GDACS Feed: {response.text[:200]}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                return [DisasterAlert(**item) for item in val]
            raise UpstreamProviderError(
                provider="GDACS Feed",
                status_code=response.status_code,
                message=f"GDACS feed returned HTTP {response.status_code}",
            )

        alerts = self.parse_feed_xml(response.text)
        await cache.set(
            cache_key,
            [a.dict() for a in alerts],
            ttl_seconds=settings.ALERT_CACHE_TTL_SECONDS,
            stale_ttl_seconds=settings.ALERT_STALE_CACHE_TTL_SECONDS,
        )
        return alerts

    def parse_feed_xml(self, xml_content: str) -> List[DisasterAlert]:
        """
        Parses GDACS RSS XML into normalized DisasterAlert models.
        """
        clean_xml = xml_content.strip()
        if not clean_xml:
            return []

        try:
            root = ET.fromstring(clean_xml)
        except ET.ParseError as e:
            logger.error(f"Malformed XML from GDACS feed: {str(e)}")
            raise UpstreamProviderError(
                provider="GDACS Feed",
                status_code=200,
                message=f"Malformed GDACS XML: {str(e)}",
            )

        ns = {
            "gdacs": "http://www.gdacs.org",
            "georss": "http://www.georss.org/georss",
            "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
        }

        alerts: List[DisasterAlert] = []
        seen_ids: set = set()

        items = root.findall(".//item")
        for item in items:
            alert = self._parse_single_item(item, ns)
            if alert and alert.alert_id not in seen_ids:
                seen_ids.add(alert.alert_id)
                alerts.append(alert)

        return alerts

    def _parse_single_item(self, elem: ET.Element, ns: Dict[str, str]) -> Optional[DisasterAlert]:
        def get_ns(tag: str, namespace: str, fallback: str = "") -> str:
            node = elem.find(f"{namespace}:{tag}", ns)
            if node is not None and node.text:
                return node.text.strip()
            return fallback

        def get_plain(tag: str, fallback: str = "") -> str:
            node = elem.find(tag)
            if node is not None and node.text:
                return node.text.strip()
            return fallback

        episode_id = get_ns("eventid", "gdacs") or get_ns("episodeid", "gdacs")
        event_type_code = get_ns("eventtype", "gdacs", "")
        title = get_plain("title", "GDACS Global Disaster Event")

        if episode_id:
            alert_id = f"gdacs-{episode_id}"
        else:
            pub_date_str = get_plain("pubDate", "")
            seed = f"{title}:{pub_date_str}"
            alert_id = "gdacs-" + hashlib.sha256(seed.encode()).hexdigest()[:16]

        event_type = GDACS_EVENT_TYPES.get(event_type_code.upper(), "Global Disaster Event")
        if event_type_code and event_type == "Global Disaster Event":
            event_type = event_type_code

        alert_level_raw = get_ns("alertlevel", "gdacs", "green").lower()
        severity = GDACS_SEVERITY_MAP.get(alert_level_raw, AlertSeverity.MINOR)

        description = get_plain("description", title)
        if "<" in description:
            import re
            description = re.sub(r"<[^>]+>", " ", description).strip()
        description = description[:500] if description else title

        country = get_ns("country", "gdacs", "")
        affected_area = country or "Global"

        georss_point = get_ns("point", "georss", "")
        polygon_coords: Optional[List[List[float]]] = None
        if georss_point:
            try:
                parts = georss_point.split()
                if len(parts) >= 2:
                    polygon_coords = [[float(parts[0]), float(parts[1])]]
            except ValueError:
                pass

        pub_date_str = get_plain("pubDate", "")
        issued_time = self._parse_datetime(pub_date_str) or datetime.utcnow()
        from_date = get_ns("fromdate", "gdacs", "")
        to_date = get_ns("todate", "gdacs", "")
        effective_time = self._parse_datetime(from_date) or issued_time

        # Note: gdacs:todate represents the observation/forecast episode end time,
        # NOT the alert bulletin expiration. Bulletins present in the live RSS feed
        # represent active disaster alerts.
        expires_time = None
        is_active = True


        iso3_code = get_ns("iso3", "gdacs", "").upper()
        country_clean = country.strip().lower()

        is_india = (
            country_clean in INDIA_EXACT_COUNTRIES
            or iso3_code == "IND"
        )

        affected_states: List[str] = []
        if is_india:
            scope = GeographicScope.NATIONAL
            affected_states = ["India"]
        else:
            scope = GeographicScope.UNKNOWN

        link = get_plain("link", None)
        guid = get_plain("guid", None)
        source_url = link or guid

        headline = f"GDACS {alert_level_raw.capitalize()} Alert: {event_type} — {country or 'Global'}"

        return DisasterAlert(
            alert_id=alert_id,
            source=AlertSource.GDACS,
            title=title,
            event_type=event_type,
            severity=severity,
            original_severity=alert_level_raw.capitalize(),
            urgency=AlertUrgency.EXPECTED,
            certainty=AlertCertainty.LIKELY,
            status=AlertStatus.ACTUAL,
            headline=headline,
            description=description,
            instruction=None,
            effective_time=effective_time,
            expires_time=expires_time,
            issued_time=issued_time,
            affected_area=affected_area,
            scope=scope,
            affected_states=affected_states,
            affected_districts=[],
            polygon_coordinates=polygon_coords,
            source_url=source_url,
            is_active=is_active,
        )

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        date_str = date_str.strip()
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                pass
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            pass
        return None

    def _india_relevance_score(self, alert: DisasterAlert) -> int:
        score = 0
        area_lower = alert.affected_area.lower()
        if area_lower in INDIA_EXACT_COUNTRIES or "india" in [s.lower() for s in alert.affected_states]:
            score += 100
        if alert.severity == AlertSeverity.EXTREME:
            score += 50
        elif alert.severity == AlertSeverity.SEVERE:
            score += 30
        elif alert.severity == AlertSeverity.MODERATE:
            score += 10
        return score

    def get_top_alerts(self, alerts: List[DisasterAlert], max_count: int = 7) -> List[DisasterAlert]:
        active = [a for a in alerts if a.is_active]
        ranked = sorted(
            active,
            key=lambda a: (
                -self._india_relevance_score(a),
                -["Unknown", "Minor", "Moderate", "Severe", "Extreme"].index(a.severity.value),
                -(a.issued_time.timestamp() if a.issued_time else 0),
            ),
        )
        return ranked[:max_count]

    async def get_alerts_for_location(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        state: Optional[str] = None,
        district: Optional[str] = None,
        active_only: bool = True,
    ) -> List[DisasterAlert]:
        alerts = await self.fetch_active_alerts()
        if active_only:
            return [a for a in alerts if a.is_active]
        return alerts


gdacs_alert_provider = GdacsAlertProvider()
