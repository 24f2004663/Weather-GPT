import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict, Any, Set, Tuple
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.errors import (
    UpstreamProviderError,
    UpstreamTimeoutError,
)
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

# Known Indian States & Union Territories for Scope Extraction
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar", "Chandigarh", "Dadra and Nagar Haveli", "Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
]

class SachetNdmaAlertProvider(BaseAlertProvider):
    """
    Official SACHET/NDMA Disaster Alert Ingestion and Normalization Adapter.
    Consumes official CAP (Common Alerting Protocol) RSS feeds, performs XML parsing,
    deduplication, expiration filtering, and geographic relevance matching.
    """
    def __init__(
        self,
        feed_url: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.feed_url = feed_url or settings.SACHET_NDMA_ALERT_FEED_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    async def fetch_active_alerts(self, force_refresh: bool = False) -> List[DisasterAlert]:
        """
        Fetches, parses, deduplicates, and caches disaster alerts from SACHET/NDMA.
        """
        cache_key = "sachet:alerts:all"
        if not force_refresh:
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                logger.debug("Cache HIT for SACHET/NDMA disaster alerts")
                return [DisasterAlert(**item) for item in cached_data]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.feed_url)
        except httpx.TimeoutException:
            logger.error(f"Timeout connecting to SACHET/NDMA feed at {self.feed_url}")
            raise UpstreamTimeoutError(provider="SACHET/NDMA Feed", timeout_seconds=self.timeout)
        except Exception as e:
            logger.error(f"Network error connecting to SACHET/NDMA: {str(e)}")
            raise UpstreamProviderError(provider="SACHET/NDMA Feed", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"SACHET/NDMA Feed HTTP {response.status_code}: {response.text}")
            raise UpstreamProviderError(
                provider="SACHET/NDMA Feed",
                status_code=response.status_code,
                message=f"SACHET/NDMA feed returned HTTP {response.status_code}"
            )

        raw_xml = response.text
        alerts = self.parse_feed_xml(raw_xml)

        # Cache normalized alerts
        await cache.set(cache_key, [a.dict() for a in alerts], ttl_seconds=settings.ALERT_CACHE_TTL_SECONDS)
        return alerts

    def parse_feed_xml(self, xml_content: str) -> List[DisasterAlert]:
        """
        Parses XML content safely into normalized DisasterAlert models.
        Handles both CAP XML elements and standard RSS item feeds with deduplication.
        """
        clean_xml = xml_content.strip()
        if not clean_xml:
            return []

        try:
            root = ET.fromstring(clean_xml)
        except Exception as e:
            logger.error(f"Malformed XML from SACHET/NDMA feed: {str(e)}")
            raise UpstreamProviderError(provider="SACHET/NDMA Feed", status_code=200, message=f"Malformed XML: {str(e)}")

        alerts: List[DisasterAlert] = []
        seen_ids: Set[str] = set()
        now = datetime.now(timezone.utc)

        # Namespaces
        ns = {
            "cap": "urn:oasis:names:tc:emergency:cap:1.2",
            "atom": "http://www.w3.org/2005/Atom"
        }

        # Check for CAP <alert> or RSS <item> / Atom <entry>
        items = root.findall(".//item") or root.findall(".//atom:entry", ns) or root.findall(".//entry")
        if not items and root.tag.endswith("alert"):
            # Root is a single CAP alert
            items = [root]

        for item in items:
            alert = self._parse_single_item(item, ns, now)
            if alert and alert.alert_id not in seen_ids:
                seen_ids.add(alert.alert_id)
                alerts.append(alert)

        return alerts

    def _parse_single_item(self, elem: ET.Element, ns: Dict[str, str], now: datetime) -> Optional[DisasterAlert]:
        """Parses an individual XML element into a DisasterAlert."""
        def get_text(tag_name: str, fallback: str = "") -> str:
            # Try with namespace
            node = elem.find(f"cap:{tag_name}", ns) or elem.find(tag_name)
            if node is not None and node.text:
                return node.text.strip()
            # Search children recursively
            for child in elem.iter():
                if child.tag.endswith(tag_name) and child.text:
                    return child.text.strip()
            return fallback

        # 1. Identifier
        guid = get_text("identifier") or get_text("guid") or get_text("id")
        title = get_text("title") or get_text("headline") or get_text("event")
        description = get_text("description") or get_text("summary") or title or "Disaster Advisory"
        pub_date_str = get_text("pubDate") or get_text("sent") or get_text("effective")

        if not guid:
            # Fallback deterministic fingerprint
            guid_seed = f"{title}:{description}:{pub_date_str}"
            guid = "sachet-" + hashlib.sha256(guid_seed.encode("utf-8")).hexdigest()[:16]

        # 2. Event Type
        event_type = get_text("event") or self._infer_event_type(title + " " + description)

        # 3. Severity & Status
        raw_severity = get_text("severity", "Unknown")
        severity = self._normalize_severity(raw_severity)
        urgency = self._normalize_urgency(get_text("urgency", "Unknown"))
        certainty = self._normalize_certainty(get_text("certainty", "Unknown"))
        raw_status = get_text("status", "Actual")
        status = self._normalize_status(raw_status)

        # 4. Instructions & Content
        headline = get_text("headline") or title
        instruction = get_text("instruction") or None
        link_url = get_text("link") or get_text("url") or None

        # 5. Timestamps
        issued_time = self._parse_datetime(pub_date_str) or datetime.utcnow()
        effective_time = self._parse_datetime(get_text("effective")) or issued_time
        expires_time = self._parse_datetime(get_text("expires"))

        # 6. Expiration Check
        is_active = True
        if status == AlertStatus.CANCELLED:
            is_active = False
        elif expires_time and datetime.now(timezone.utc) > (expires_time if expires_time.tzinfo else expires_time.replace(tzinfo=timezone.utc)):
            is_active = False

        # 7. Geographic Information
        area_desc = get_text("areaDesc") or get_text("area") or description or "India"
        states, districts, scope = self._extract_geographic_scope(area_desc + " " + title)

        return DisasterAlert(
            alert_id=guid,
            source=AlertSource.SACHET_NDMA,
            title=title or "Official Disaster Alert",
            event_type=event_type,
            severity=severity,
            original_severity=raw_severity,
            urgency=urgency,
            certainty=certainty,
            status=status,
            headline=headline,
            description=description,
            instruction=instruction,
            effective_time=effective_time,
            expires_time=expires_time,
            issued_time=issued_time,
            affected_area=area_desc,
            scope=scope,
            affected_states=states,
            affected_districts=districts,
            source_url=link_url,
            is_active=is_active
        )

    def _normalize_severity(self, raw: str) -> AlertSeverity:
        r = raw.strip().lower()
        if "extreme" in r:
            return AlertSeverity.EXTREME
        elif "severe" in r or "high" in r or "red" in r:
            return AlertSeverity.SEVERE
        elif "moderate" in r or "medium" in r or "orange" in r:
            return AlertSeverity.MODERATE
        elif "minor" in r or "low" in r or "yellow" in r:
            return AlertSeverity.MINOR
        return AlertSeverity.UNKNOWN

    def _normalize_urgency(self, raw: str) -> AlertUrgency:
        r = raw.strip().lower()
        if "immediate" in r:
            return AlertUrgency.IMMEDIATE
        elif "expected" in r:
            return AlertUrgency.EXPECTED
        elif "future" in r:
            return AlertUrgency.FUTURE
        elif "past" in r:
            return AlertUrgency.PAST
        return AlertUrgency.UNKNOWN

    def _normalize_certainty(self, raw: str) -> AlertCertainty:
        r = raw.strip().lower()
        if "observed" in r:
            return AlertCertainty.OBSERVED
        elif "likely" in r:
            return AlertCertainty.LIKELY
        elif "possible" in r:
            return AlertCertainty.POSSIBLE
        elif "unlikely" in r:
            return AlertCertainty.UNLIKELY
        return AlertCertainty.UNKNOWN

    def _normalize_status(self, raw: str) -> AlertStatus:
        r = raw.strip().lower()
        if "cancel" in r:
            return AlertStatus.CANCELLED
        elif "test" in r:
            return AlertStatus.TEST
        elif "draft" in r:
            return AlertStatus.DRAFT
        elif "exercise" in r:
            return AlertStatus.EXERCISE
        elif "system" in r:
            return AlertStatus.SYSTEM
        return AlertStatus.ACTUAL

    def _infer_event_type(self, text: str) -> str:
        t = text.lower()
        if "cyclone" in t:
            return "Cyclone"
        elif "flood" in t or "inundation" in t:
            return "Flood"
        elif "heavy rain" in t or "rainfall" in t or "downpour" in t:
            return "Heavy Rain"
        elif "thunderstorm" in t or "lightning" in t:
            return "Thunderstorm & Lightning"
        elif "heat" in t or "heatwave" in t:
            return "Heat Wave"
        elif "cold" in t or "coldwave" in t:
            return "Cold Wave"
        elif "earthquake" in t or "tremor" in t:
            return "Earthquake"
        elif "tsunami" in t:
            return "Tsunami"
        elif "landslide" in t:
            return "Landslide"
        return "Severe Weather"

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        date_str = date_str.strip()
        # 1. Try ISO 8601
        try:
            return datetime.fromisoformat(date_str)
        except Exception:
            pass
        # 2. Try RFC 2822
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            pass
        return None

    def _extract_geographic_scope(self, text: str) -> Tuple[List[str], List[str], GeographicScope]:
        states_found: List[str] = []
        text_lower = text.lower()

        for s in INDIAN_STATES:
            if s.lower() in text_lower:
                states_found.append(s)

        districts_found: List[str] = []
        # Common key coastal/metropolitan districts in India
        known_districts = [
            "Chennai", "Tiruvallur", "Kanchipuram", "Chengalpattu", "Cuddalore",
            "Nagapattinam", "Coimbatore", "Madurai", "Mumbai", "Thane", "Raigad",
            "Pune", "Bengaluru", "Hyderabad", "Kolkata", "Howrah", "Puri", "Cuttack",
            "Visakhapatnam", "Ernakulam", "Thiruvananthapuram", "Ahmedabad", "Surat"
        ]
        for d in known_districts:
            if d.lower() in text_lower:
                districts_found.append(d)

        if districts_found:
            scope = GeographicScope.DISTRICT
        elif states_found:
            scope = GeographicScope.STATE
        elif "india" in text_lower or "nationwide" in text_lower:
            scope = GeographicScope.NATIONAL
        else:
            scope = GeographicScope.UNKNOWN

        return states_found, districts_found, scope

    async def get_alerts_for_location(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        state: Optional[str] = None,
        district: Optional[str] = None,
        active_only: bool = True
    ) -> List[DisasterAlert]:
        """
        Retrieves active alerts and filters them based on geographical relevance.
        """
        all_alerts = await self.fetch_active_alerts()
        
        filtered: List[DisasterAlert] = []
        for alert in all_alerts:
            if active_only and not alert.is_active:
                continue

            # If no location filters supplied, include alert
            if not state and not district and lat is None:
                filtered.append(alert)
                continue

            matched = False

            # 1. District matching (highest precision)
            if district:
                d_clean = district.strip().lower()
                if any(d_clean in d.lower() for d in alert.affected_districts):
                    matched = True
                elif d_clean in alert.affected_area.lower() or d_clean in alert.description.lower():
                    matched = True

            # 2. State matching
            if not matched and state:
                s_clean = state.strip().lower()
                if any(s_clean in s.lower() for s in alert.affected_states):
                    matched = True
                elif s_clean in alert.affected_area.lower() or s_clean in alert.description.lower():
                    matched = True

            # 3. National-scope matching
            if not matched and alert.scope == GeographicScope.NATIONAL:
                matched = True

            if matched:
                filtered.append(alert)

        return filtered

sachet_alert_provider = SachetNdmaAlertProvider()
