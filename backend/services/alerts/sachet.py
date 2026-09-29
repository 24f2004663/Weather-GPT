import asyncio
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Dict, Any, Set, Tuple
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
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

# Approximate bounding boxes (lat_min, lat_max, lon_min, lon_max) for Indian states
# and UTs, used only to turn a bare lat/lon into candidate state names for alert
# matching. SACHET's per-alert polygon endpoint is not publicly fetchable and no
# reverse geocoder is available in-stack, so these boxes are deliberately generous:
# boxes overlap, and a point may resolve to several states. Over-inclusion is the
# intended failure direction -- showing a neighbouring state's warning is recoverable,
# withholding a live one is not. These are a targeting aid, never authoritative geometry.
STATE_BOUNDING_BOXES: Dict[str, Tuple[float, float, float, float]] = {
    "Andhra Pradesh": (12.6, 19.9, 76.7, 84.8),
    "Arunachal Pradesh": (26.6, 29.5, 91.5, 97.4),
    "Assam": (24.1, 28.2, 89.7, 96.0),
    "Bihar": (24.2, 27.5, 83.3, 88.3),
    "Chhattisgarh": (17.8, 24.1, 80.2, 84.4),
    "Goa": (14.8, 15.8, 73.6, 74.4),
    "Gujarat": (20.1, 24.7, 68.1, 74.5),
    "Haryana": (27.6, 30.9, 74.4, 77.6),
    "Himachal Pradesh": (30.3, 33.3, 75.5, 79.1),
    "Jharkhand": (21.9, 25.4, 83.3, 87.9),
    "Karnataka": (11.5, 18.5, 74.0, 78.6),
    "Kerala": (8.2, 12.8, 74.8, 77.4),
    "Madhya Pradesh": (21.0, 26.9, 74.0, 82.8),
    "Maharashtra": (15.6, 22.1, 72.6, 80.9),
    "Manipur": (23.8, 25.7, 92.9, 94.8),
    "Meghalaya": (25.0, 26.2, 89.8, 92.9),
    "Mizoram": (21.9, 24.6, 92.2, 93.5),
    "Nagaland": (25.2, 27.1, 93.3, 95.3),
    "Odisha": (17.7, 22.6, 81.3, 87.6),
    "Punjab": (29.5, 32.6, 73.8, 76.9),
    "Rajasthan": (23.0, 30.2, 69.4, 78.3),
    "Sikkim": (27.0, 28.2, 88.0, 88.9),
    "Tamil Nadu": (8.0, 13.6, 76.2, 80.4),
    "Telangana": (15.8, 19.9, 77.2, 81.4),
    "Tripura": (22.9, 24.6, 91.0, 92.4),
    "Uttar Pradesh": (23.8, 30.5, 77.0, 84.7),
    "Uttarakhand": (28.7, 31.5, 77.5, 81.1),
    "West Bengal": (21.4, 27.3, 85.8, 89.9),
    "Andaman and Nicobar": (6.6, 13.7, 92.2, 94.3),
    "Chandigarh": (30.6, 30.8, 76.6, 76.9),
    "Dadra and Nagar Haveli": (20.0, 20.5, 72.8, 73.3),
    "Daman and Diu": (20.3, 20.8, 70.8, 73.0),
    "Delhi": (28.4, 28.9, 76.8, 77.4),
    "Jammu and Kashmir": (32.2, 35.7, 73.8, 79.3),
    "Ladakh": (32.2, 36.1, 75.8, 80.4),
    "Lakshadweep": (8.2, 12.4, 71.7, 74.0),
    "Puducherry": (9.8, 12.1, 74.8, 79.9),
}


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
        Fetches, parses, deduplicates, and caches disaster alerts from SACHET/NDMA
        with strict 15-minute maximum emergency staleness policy.
        """
        cache_key = "sachet:alerts:all"
        if not force_refresh:
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                logger.debug("[Cache HIT] SACHET/NDMA disaster alerts")
                return [DisasterAlert(**item) for item in cached_data]

        try:
            client = await http_client_manager.get_client()
            response = await client.get(self.feed_url, timeout=self.timeout)

        except httpx.TimeoutException:
            logger.error(f"[Upstream timeout] SACHET/NDMA feed at {self.feed_url}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning("[Cache STALE FALLBACK] Serving recent alerts within 15-minute emergency window")
                return [DisasterAlert(**item) for item in val]
            raise UpstreamTimeoutError(provider="SACHET/NDMA Feed", timeout_seconds=self.timeout)

        except Exception as e:
            logger.error(f"[Network error] SACHET/NDMA: {str(e)}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning("[Cache STALE FALLBACK] Serving recent alerts within 15-minute emergency window")
                return [DisasterAlert(**item) for item in val]
            raise UpstreamProviderError(provider="SACHET/NDMA Feed", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"[Upstream {response.status_code}] SACHET/NDMA Feed: {response.text[:200]}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning("[Cache STALE FALLBACK] Serving recent alerts within 15-minute emergency window")
                return [DisasterAlert(**item) for item in val]
            raise UpstreamProviderError(
                provider="SACHET/NDMA Feed",
                status_code=response.status_code,
                message=f"SACHET/NDMA feed returned HTTP {response.status_code}"
            )

        raw_xml = response.text
        alerts = self.parse_feed_xml(raw_xml)

        # Hydrate severity/urgency/expiry/instruction/areaDesc from each alert's CAP
        # document before caching, so every consumer reads fully-populated alerts.
        alerts = await self.enrich_with_cap_details(alerts)

        # Cache with fresh TTL (5 min) and bounded emergency stale TTL (15 min)
        await cache.set(
            cache_key,
            [a.dict() for a in alerts],
            ttl_seconds=settings.ALERT_CACHE_TTL_SECONDS,
            stale_ttl_seconds=settings.ALERT_STALE_CACHE_TTL_SECONDS
        )
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
            node = elem.find(f"cap:{tag_name}", ns)
            if node is None:
                node = elem.find(tag_name)
            if node is not None and node.text:
                return node.text.strip()
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
        try:
            return datetime.fromisoformat(date_str)
        except Exception:
            pass
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

    # ------------------------------------------------------------------
    # CAP detail enrichment
    #
    # The public RSS index exposes only title/category/link/author/guid/pubDate.
    # Every field that makes an alert actionable -- severity, urgency, certainty,
    # expiry, official instruction text and a structured areaDesc -- lives in the
    # per-alert CAP 1.2 document linked from each item. Without this step every
    # alert normalizes to severity=Unknown with no expiry, which disables severity
    # targeting, expiry filtering and escalation detection downstream.
    # ------------------------------------------------------------------
    def parse_cap_detail(self, xml_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses a single CAP 1.2 alert document into a flat overlay dict.

        A CAP bulletin carries one <cap:info> block per language. Structured fields
        are read from the English block when present (SACHET emits en-IN alongside a
        regional language); the regional block is preserved verbatim for display.
        """
        try:
            root = ET.fromstring(xml_text.strip())
        except Exception as e:
            logger.warning(f"[SACHET CAP] Malformed CAP document: {e}")
            return None

        ns = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

        def txt(node: Optional[ET.Element], tag: str) -> str:
            if node is None:
                return ""
            el = node.find(f"cap:{tag}", ns)
            if el is None:
                el = node.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        infos = root.findall("cap:info", ns) or root.findall("info")
        if not infos:
            return None

        def lang_of(i: ET.Element) -> str:
            return txt(i, "language").lower()

        english = next((i for i in infos if lang_of(i).startswith("en")), None)
        primary = english if english is not None else infos[0]
        local = next((i for i in infos if i is not primary and lang_of(i)), None)

        areas: List[str] = []
        for area in (primary.findall("cap:area", ns) or primary.findall("area")):
            desc = txt(area, "areaDesc")
            if desc:
                areas.append(desc)

        return {
            "status": txt(root, "status"),
            "severity": txt(primary, "severity"),
            "urgency": txt(primary, "urgency"),
            "certainty": txt(primary, "certainty"),
            "event": txt(primary, "event"),
            "headline": txt(primary, "headline"),
            "description": txt(primary, "description"),
            "instruction": txt(primary, "instruction"),
            "effective": txt(primary, "effective"),
            "expires": txt(primary, "expires"),
            "area_desc": "; ".join(areas),
            "headline_local": txt(local, "headline") if local is not None else "",
            "description_local": txt(local, "description") if local is not None else "",
            "local_language": lang_of(local) if local is not None else "",
        }

    def apply_cap_detail(self, alert: DisasterAlert, detail: Dict[str, Any], now: datetime) -> DisasterAlert:
        """Overlays CAP-derived fields onto an RSS-derived alert, in place."""
        if detail.get("severity"):
            alert.severity = self._normalize_severity(detail["severity"])
            alert.original_severity = detail["severity"]
        if detail.get("urgency"):
            alert.urgency = self._normalize_urgency(detail["urgency"])
        if detail.get("certainty"):
            alert.certainty = self._normalize_certainty(detail["certainty"])
        if detail.get("status"):
            alert.status = self._normalize_status(detail["status"])
        if detail.get("event"):
            alert.event_type = detail["event"]
        if detail.get("headline"):
            alert.headline = detail["headline"]
        if detail.get("description"):
            alert.description = detail["description"]
        if detail.get("instruction"):
            alert.instruction = detail["instruction"]

        effective = self._parse_datetime(detail.get("effective"))
        if effective:
            alert.effective_time = effective
        expires = self._parse_datetime(detail.get("expires"))
        if expires:
            alert.expires_time = expires

        # Structured areaDesc is far more reliable than scraping a headline, and is
        # emitted in English even when the bulletin headline is in a regional script.
        area_desc = detail.get("area_desc") or ""
        if area_desc:
            alert.affected_area = area_desc
            states, districts, scope = self._extract_geographic_scope(
                f"{area_desc} {detail.get('headline') or ''}"
            )
            if states:
                alert.affected_states = states
            if districts:
                alert.affected_districts = districts
            if scope != GeographicScope.UNKNOWN:
                alert.scope = scope

        if detail.get("headline_local"):
            alert.headline_local = detail["headline_local"]
        if detail.get("description_local"):
            alert.description_local = detail["description_local"]
        if detail.get("local_language"):
            alert.local_language = detail["local_language"]

        # Re-evaluate liveness now that a real expiry and status are known.
        alert.is_active = True
        if alert.status == AlertStatus.CANCELLED:
            alert.is_active = False
        elif alert.expires_time is not None:
            exp = alert.expires_time
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                alert.is_active = False
        return alert

    async def _fetch_cap_detail(self, alert: DisasterAlert) -> Optional[Dict[str, Any]]:
        """Fetches and caches one CAP document. Returns None on any failure."""
        url = alert.source_url
        if not url:
            return None

        cache_key = f"sachet:cap:{alert.alert_id}"
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = await http_client_manager.get_client()
            response = await client.get(url, timeout=settings.SACHET_CAP_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning(f"[SACHET CAP] Fetch failed for {alert.alert_id}: {e}")
            return None

        if response.status_code != 200:
            logger.warning(f"[SACHET CAP] HTTP {response.status_code} for {alert.alert_id}")
            return None

        detail = self.parse_cap_detail(response.text)
        if detail is None:
            return None

        await cache.set(cache_key, detail, ttl_seconds=settings.SACHET_CAP_DETAIL_TTL_SECONDS)
        return detail

    async def enrich_with_cap_details(self, alerts: List[DisasterAlert]) -> List[DisasterAlert]:
        """
        Concurrently enriches alerts from their CAP documents under a bounded
        semaphore. A failed or malformed CAP fetch leaves that alert exactly as the
        RSS index produced it -- degraded detail is always preferable to dropping a
        live emergency bulletin.
        """
        if not settings.SACHET_CAP_ENRICH_ENABLED or not alerts:
            return alerts

        now = datetime.now(timezone.utc)
        semaphore = asyncio.Semaphore(max(1, settings.SACHET_CAP_MAX_CONCURRENCY))

        async def enrich_one(alert: DisasterAlert) -> None:
            async with semaphore:
                detail = await self._fetch_cap_detail(alert)
            if detail:
                self.apply_cap_detail(alert, detail, now)

        results = await asyncio.gather(
            *(enrich_one(a) for a in alerts), return_exceptions=True
        )
        failures = sum(1 for r in results if isinstance(r, Exception))
        enriched = sum(1 for a in alerts if a.severity != AlertSeverity.UNKNOWN)
        logger.info(
            f"[SACHET CAP] Enriched {enriched}/{len(alerts)} alerts with CAP detail "
            f"({failures} exceptions)"
        )
        return alerts

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

        # Resolve bare coordinates into candidate state names so that lat/lon is an
        # actual matching criterion. Previously lat/lon was accepted and then never
        # read, so a coordinates-only query matched nothing but NATIONAL-scope alerts
        # -- strictly worse than passing no filter at all.
        coord_states: List[str] = []
        if lat is not None and lon is not None:
            coord_states = self.states_for_point(lat, lon)
            if not coord_states:
                logger.info(
                    f"[SACHET] Coordinates ({lat:.3f}, {lon:.3f}) fall outside all known "
                    f"Indian state boxes; coordinate filtering will not narrow results."
                )

        has_geo_filter = bool(state or district or coord_states)

        filtered: List[DisasterAlert] = []
        for alert in all_alerts:
            if active_only and not alert.is_active:
                continue

            # No usable geographic criterion: never silently narrow. A coordinates-only
            # query that could not be resolved falls through to the unfiltered list
            # rather than returning an empty one.
            if not has_geo_filter:
                filtered.append(alert)
                continue

            matched = False

            if district:
                d_clean = district.strip().lower()
                if any(d_clean in d.lower() for d in alert.affected_districts):
                    matched = True
                elif d_clean in alert.affected_area.lower() or d_clean in alert.description.lower():
                    matched = True

            if not matched and state:
                s_clean = state.strip().lower()
                if any(s_clean in s.lower() for s in alert.affected_states):
                    matched = True
                elif s_clean in alert.affected_area.lower() or s_clean in alert.description.lower():
                    matched = True

            if not matched and coord_states:
                for cs in coord_states:
                    cs_clean = cs.lower()
                    if any(cs_clean in s.lower() for s in alert.affected_states):
                        matched = True
                        break
                    if cs_clean in alert.affected_area.lower():
                        matched = True
                        break

            if not matched and alert.scope == GeographicScope.NATIONAL:
                matched = True

            if matched:
                filtered.append(alert)

        return filtered

    def states_for_point(self, lat: float, lon: float) -> List[str]:
        """
        Returns every Indian state or UT whose approximate bounding box contains the
        point. Boxes overlap, so several names may be returned; callers treat the
        result as a candidate set, not a definitive administrative lookup.
        """
        return [
            name
            for name, (lat_min, lat_max, lon_min, lon_max) in STATE_BOUNDING_BOXES.items()
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
        ]

sachet_alert_provider = SachetNdmaAlertProvider()
