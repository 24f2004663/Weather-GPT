import asyncio
from typing import List, Dict, Tuple, Set, Optional
from datetime import datetime

from backend.core.logging import logger
from backend.schemas.alerts import DisasterAlert, AlertSeverity
from backend.services.alerts.sachet import sachet_alert_provider
from backend.services.alerts.gdacs import gdacs_alert_provider
from backend.services.ai.alert_message import generate_alert_message
from backend.services.notifications.events import alert_event_bus
from backend.db.supabase import supabase_client

# Severity rank order for escalation checking
SEVERITY_RANK: Dict[AlertSeverity, int] = {
    AlertSeverity.UNKNOWN: 0,
    AlertSeverity.MINOR: 1,
    AlertSeverity.MODERATE: 2,
    AlertSeverity.SEVERE: 3,
    AlertSeverity.EXTREME: 4,
}


class AlertIngestionEngine:
    """
    Emergency Alert Ingestion & Pipeline Engine.
    Polls real SACHET/NDMA and GDACS feeds concurrently, normalizes alerts,
    enforces deduplication via Supabase seen_alerts (with cross-restart persistence),
    detects severity escalations, generates user-facing alert messages via Gemini,
    and emits verified alerts to the Notification Event Bus.
    """

    def __init__(self):
        # In-memory fallback set for deduplication if Supabase is unconfigured
        self._in_memory_seen: Dict[str, AlertSeverity] = {}
        self._lock = asyncio.Lock()

    async def poll_and_dispatch(self) -> Dict[str, int]:
        """
        Executes a full ingestion, normalization, deduplication, and notification cycle.
        """
        logger.info("[Alert Engine] Starting emergency alert ingestion poll cycle...")

        # 1. Concurrently fetch SACHET and GDACS feeds with exception isolation
        sachet_task = sachet_alert_provider.fetch_active_alerts(force_refresh=True)
        gdacs_task = gdacs_alert_provider.fetch_active_alerts(force_refresh=True)

        results = await asyncio.gather(sachet_task, gdacs_task, return_exceptions=True)

        all_alerts: List[DisasterAlert] = []

        # Process SACHET results
        if isinstance(results[0], list):
            all_alerts.extend(results[0])
            logger.info(f"[Alert Engine] Fetched {len(results[0])} alerts from SACHET/NDMA")
        elif isinstance(results[0], Exception):
            logger.error(f"[Alert Engine] SACHET ingestion error: {str(results[0])}")

        # Process GDACS results
        if isinstance(results[1], list):
            all_alerts.extend(results[1])
            logger.info(f"[Alert Engine] Fetched {len(results[1])} alerts from GDACS")
        elif isinstance(results[1], Exception):
            logger.error(f"[Alert Engine] GDACS ingestion error: {str(results[1])}")

        dispatched_count = 0
        skipped_count = 0
        inactive_count = 0

        for alert in all_alerts:
            # Handle inactive / expired / cancelled alerts
            if not alert.is_active:
                inactive_count += 1
                await self._mark_inactive(alert.alert_id)
                continue

            # Deduplication check
            should_dispatch, is_escalation = await self._should_dispatch(alert)

            if not should_dispatch:
                skipped_count += 1
                continue

            # Generate Gemini alert message (faithful to source, no fabrication)
            try:
                alert_text = await generate_alert_message(alert, language="en")
                if alert_text:
                    alert.headline = alert_text
            except Exception as e:
                logger.error(f"[Alert Engine] Gemini message generation error for {alert.alert_id}: {str(e)}")

            # Emit alert event to notification bus
            try:
                await alert_event_bus.emit_alert_triggered(alert)
                dispatched_count += 1
                logger.info(f"[Alert Engine] Dispatched alert notification: {alert.alert_id} ({alert.title}) [Escalation={is_escalation}]")
            except Exception as e:
                logger.error(f"[Alert Engine] Error emitting alert event: {str(e)}")

            # Mark alert as seen in persistent store
            await self._mark_seen(alert)

        summary = {
            "total_ingested": len(all_alerts),
            "dispatched": dispatched_count,
            "skipped_dedup": skipped_count,
            "inactive_skipped": inactive_count,
        }
        logger.info(f"[Alert Engine] Poll cycle complete: {summary}")
        return summary

    async def _should_dispatch(self, alert: DisasterAlert) -> Tuple[bool, bool]:
        """
        Determines if an alert should trigger notifications based on deduplication.
        Returns (should_dispatch, is_escalation).
        """
        alert_id = alert.alert_id
        curr_sev = alert.severity

        # Check Supabase first
        if supabase_client.is_configured():
            has_seen, prev_sev_str = await supabase_client.has_seen_alert(alert_id)
            if not has_seen:
                return True, False  # Brand new alert

            # Convert prev_sev_str to AlertSeverity
            try:
                prev_sev = AlertSeverity(prev_sev_str) if prev_sev_str else AlertSeverity.UNKNOWN
            except ValueError:
                prev_sev = AlertSeverity.UNKNOWN

            # Check if severity escalated
            if SEVERITY_RANK.get(curr_sev, 0) > SEVERITY_RANK.get(prev_sev, 0):
                logger.info(f"[Alert Engine] Alert severity escalated: {alert_id} ({prev_sev.value} -> {curr_sev.value})")
                return True, True

            return False, False  # Unchanged alert -> skip

        # In-memory fallback
        async with self._lock:
            if alert_id not in self._in_memory_seen:
                return True, False

            prev_sev = self._in_memory_seen[alert_id]
            if SEVERITY_RANK.get(curr_sev, 0) > SEVERITY_RANK.get(prev_sev, 0):
                return True, True

            return False, False

    async def _mark_seen(self, alert: DisasterAlert) -> None:
        alert_id = alert.alert_id
        source = alert.source.value if hasattr(alert.source, "value") else str(alert.source)
        sev_str = alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity)

        if supabase_client.is_configured():
            await supabase_client.mark_alert_seen(alert_id, source, sev_str, is_active=True)

        async with self._lock:
            self._in_memory_seen[alert_id] = alert.severity

    async def _mark_inactive(self, alert_id: str) -> None:
        if supabase_client.is_configured():
            await supabase_client.mark_alert_inactive(alert_id)

        async with self._lock:
            if alert_id in self._in_memory_seen:
                del self._in_memory_seen[alert_id]


alert_ingestion_engine = AlertIngestionEngine()
