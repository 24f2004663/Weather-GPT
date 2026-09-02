import asyncio
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

from backend.core.config import settings
from backend.core.logging import logger
from backend.schemas.alerts import DisasterAlert, AlertSeverity
from backend.schemas.notifications import (
    NotificationSubscription,
    SubscriptionRequest,
    NotificationChannel,
    NotificationStatus,
    NotificationPayload,
    NotificationRecord,
    DisasterAlertTriggeredEvent,
    NotificationPreviewResponse,
    mask_phone_number,
)
from backend.services.notifications.whatsapp import whatsapp_notification_adapter
from backend.services.notifications.baileys_whatsapp import baileys_whatsapp_adapter
from backend.services.notifications.exotel import exotel_sms_adapter
from backend.services.notifications.textbee_sms import textbee_sms_adapter
from backend.services.notifications.voice import exotel_voice_adapter
from backend.services.notifications.twilio_sms import twilio_sms_adapter
from backend.services.notifications.twilio_voice import twilio_voice_adapter
from backend.services.notifications.twilio_whatsapp import twilio_whatsapp_adapter
from backend.services.notifications.web_push import web_push_adapter
from fastapi import HTTPException, status
from backend.services.notifications.formatter import (
    format_whatsapp_alert,
    format_sms_alert,
    format_voice_script,
)
from backend.db.supabase import supabase_client

class NotificationOrchestrator:
    """
    Central Notification Orchestrator.
    Handles user subscriptions with Supabase as the sole authoritative persistent database,
    severity & geographic filtering, rate limiting, idempotency enforcement,
    multilingual template selection, and fault-tolerant multi-channel dispatch.
    """
    def __init__(self):
        self._sent_idempotency_keys: Dict[str, float] = {} # idempotency_key -> timestamp
        self._recipient_hourly_counts: Dict[str, List[float]] = {} # recipient -> list of timestamps
        self._audit_records: List[NotificationRecord] = []
        self._lock = asyncio.Lock()

    async def save_subscription(self, req: SubscriptionRequest) -> NotificationSubscription:
        """
        Saves or updates user notification preferences in Supabase as the sole authoritative source of truth.
        Raises HTTPException(503) if Supabase write fails or is unconfigured.
        """
        sub_id = str(uuid.uuid4())
        existing = None
        if supabase_client.is_configured():
            existing = await supabase_client.get_subscription(req.user_identifier)
            if existing:
                sub_id = existing.subscription_id

        sub = NotificationSubscription(
            subscription_id=sub_id,
            user_identifier=req.user_identifier,
            phone_number=req.phone_number,
            whatsapp_number=req.whatsapp_number or req.phone_number,
            preferred_language=req.preferred_language,
            enabled_channels=req.enabled_channels,
            min_severity_threshold=req.min_severity_threshold,
            target_states=req.target_states,
            target_districts=req.target_districts,
            push_subscription=req.push_subscription,
            is_opted_in=req.is_opted_in,
            created_at=existing.created_at if existing else datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        if not supabase_client.is_configured():
            logger.error("Supabase is not configured; cannot persist subscription.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database persistence error: Supabase is not configured."
            )

        success = await supabase_client.save_subscription(sub)
        if not success:
            logger.error(f"Failed to persist subscription to Supabase for user: {req.user_identifier}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to persist subscription to database. Please try again."
            )

        logger.info(f"Notification subscription persisted in Supabase for user: {req.user_identifier} (Channels: {req.enabled_channels})")
        return sub

    async def get_subscription(self, user_identifier: str) -> Optional[NotificationSubscription]:
        """Retrieves subscription directly from Supabase (sole authoritative source of truth)."""
        if not supabase_client.is_configured():
            return None
        return await supabase_client.get_subscription(user_identifier)

    async def delete_subscription(self, user_identifier: str) -> bool:
        """Deactivates/deletes user subscription directly in Supabase."""
        if not supabase_client.is_configured():
            return False
        return await supabase_client.delete_subscription(user_identifier)

    async def is_phone_subscribed(self, phone: str) -> bool:
        """
        Checks whether a normalized phone number belongs to an active, opted-in Emergency Alert subscriber
        directly against Supabase (sole authoritative source of truth).
        """
        if not supabase_client.is_configured():
            return False
        return await supabase_client.is_phone_subscribed(phone)

    async def handle_alert_event(self, event: DisasterAlertTriggeredEvent) -> List[NotificationRecord]:
        """
        Orchestrates concurrent, fault-isolated multi-channel delivery when an official disaster alert occurs.
        Reads active subscribers directly from Supabase.
        """
        alert = event.alert
        logger.info(f"Orchestrator processing alert: {alert.alert_id} ({alert.title}) - {alert.severity.value}")

        all_subs = []
        if supabase_client.is_configured():
            all_subs = await supabase_client.get_all_active_subscriptions()

        tasks = []
        # Phase 2 active notification channels (WhatsApp, Web Push, SMS active; Voice/IVR remains Phase 3)
        PHASE_2_ACTIVE_CHANNELS = {NotificationChannel.WHATSAPP, NotificationChannel.WEB_PUSH, NotificationChannel.SMS}

        for sub in all_subs:
            if not sub.is_opted_in:
                continue

            # 1. Severity Threshold Filter
            if not self._check_severity_threshold(alert.severity, sub.min_severity_threshold):
                continue

            # 2. Geographic Relevance Filter
            if not self._check_geographic_match(alert, sub):
                continue

            # 3. Schedule delivery tasks for Phase 2 active channels
            for channel in sub.enabled_channels:
                if channel in PHASE_2_ACTIVE_CHANNELS:
                    tasks.append(self._process_single_delivery(alert, sub, channel))


        if not tasks:
            return []

        # Execute deliveries concurrently with exception isolation
        results = await asyncio.gather(*tasks, return_exceptions=True)
        records: List[NotificationRecord] = []
        for res in results:
            if isinstance(res, NotificationRecord):
                records.append(res)
            elif isinstance(res, Exception):
                logger.error(f"Notification delivery task failed: {str(res)}")

        return records

    async def _process_single_delivery(
        self,
        alert: DisasterAlert,
        sub: NotificationSubscription,
        channel: NotificationChannel
    ) -> Optional[NotificationRecord]:
        """Processes delivery for a single subscriber and channel with idempotency and rate limits."""
        recipient = None
        if channel in [NotificationChannel.SMS, NotificationChannel.VOICE_IVR]:
            recipient = sub.phone_number
        elif channel == NotificationChannel.WHATSAPP:
            recipient = sub.whatsapp_number or sub.phone_number
        elif channel == NotificationChannel.WEB_PUSH:
            recipient = sub.user_identifier

        if not recipient:
            return None

        # Idempotency check (prevent duplicate dispatches within 24 hours)
        idempotency_key = f"{alert.alert_id}:{recipient}:{channel.value}"
        if await self._is_duplicate(idempotency_key):
            logger.debug(f"Duplicate notification suppressed by idempotency key: {idempotency_key}")
            return None

        # Rate limit check (max 5 alerts per recipient per hour)
        if await self._is_rate_limited(recipient):
            logger.warning(f"Rate limit exceeded for recipient: {mask_phone_number(recipient)}. Skipping alert {alert.alert_id}")
            return None

        # Format message in subscriber's language
        formatted_message = self._format_message_for_channel(alert, channel, sub.preferred_language)

        payload = NotificationPayload(
            recipient_identifier=recipient,
            channel=channel,
            title=alert.title,
            message=formatted_message,
            priority="high",
            alert_id=alert.alert_id,
            language=sub.preferred_language,
            push_subscription=sub.push_subscription if channel == NotificationChannel.WEB_PUSH else None
        )

        try:
            delivery_status = await self._dispatch_to_adapter(channel, payload)
        except Exception as e:
            logger.error(f"Provider adapter error on channel {channel.value}: {str(e)}")
            delivery_status = None

        record = NotificationRecord(
            notification_id=delivery_status.notification_id if delivery_status else str(uuid.uuid4()),
            alert_id=alert.alert_id,
            channel=channel,
            recipient=mask_phone_number(recipient) or recipient,
            status=delivery_status.status if delivery_status else NotificationStatus.FAILED,
            provider=self._get_provider_name(channel),
            sent_at=datetime.utcnow() if delivery_status and delivery_status.status in [NotificationStatus.SENT, NotificationStatus.SIMULATED] else None,
            failed_at=datetime.utcnow() if not delivery_status or delivery_status.status == NotificationStatus.FAILED else None,
            provider_message_id=delivery_status.provider_reference if delivery_status else None,
            error_message=delivery_status.error_message if delivery_status else "Unhandled adapter exception",
            idempotency_key=idempotency_key,
            dry_run=delivery_status.is_simulated if delivery_status else settings.NOTIFICATION_DRY_RUN
        )

        await self._record_dispatch(idempotency_key, recipient, record)
        return record

    def _check_severity_threshold(self, alert_sev: AlertSeverity, min_threshold: AlertSeverity) -> bool:
        severity_rank = {
            AlertSeverity.UNKNOWN: 0,
            AlertSeverity.MINOR: 1,
            AlertSeverity.MODERATE: 2,
            AlertSeverity.SEVERE: 3,
            AlertSeverity.EXTREME: 4,
        }
        return severity_rank.get(alert_sev, 0) >= severity_rank.get(min_threshold, 3)

    def _check_geographic_match(self, alert: DisasterAlert, sub: NotificationSubscription) -> bool:
        # If subscriber specified no region filters, match all alerts
        if not sub.target_states and not sub.target_districts:
            return True

        # Check district match
        if sub.target_districts:
            for d in sub.target_districts:
                if d.lower() in [ad.lower() for ad in alert.affected_districts] or d.lower() in alert.affected_area.lower():
                    return True

        # Check state match
        if sub.target_states:
            for s in sub.target_states:
                if s.lower() in [ast.lower() for ast in alert.affected_states] or s.lower() in alert.affected_area.lower():
                    return True

        return False

    async def _is_duplicate(self, idempotency_key: str, ttl_seconds: float = 86400.0) -> bool:
        now = time.time()
        async with self._lock:
            if idempotency_key in self._sent_idempotency_keys:
                last_sent = self._sent_idempotency_keys[idempotency_key]
                if now - last_sent < ttl_seconds:
                    return True
            return False

    async def _is_rate_limited(self, recipient: str) -> bool:
        """
        Enforces maximum notifications per recipient per hour.
        Prunes timestamps older than 3600s to prevent unbounded memory growth.
        """
        now = time.time()
        one_hour_ago = now - 3600.0
        max_limit = settings.MAX_NOTIFICATIONS_PER_RECIPIENT_PER_HOUR

        async with self._lock:
            timestamps = self._recipient_hourly_counts.get(recipient, [])
            recent_timestamps = [ts for ts in timestamps if ts > one_hour_ago]
            self._recipient_hourly_counts[recipient] = recent_timestamps
            return len(recent_timestamps) >= max_limit

    async def cleanup_expired_tracking(self) -> int:
        """
        Purges expired rate-limit tracking entries and old idempotency keys.
        """
        now = time.time()
        one_hour_ago = now - 3600.0
        one_day_ago = now - 86400.0
        purged = 0

        async with self._lock:
            # Clean up recipient counts
            empty_recipients = []
            for recipient, timestamps in self._recipient_hourly_counts.items():
                recent = [ts for ts in timestamps if ts > one_hour_ago]
                if recent:
                    self._recipient_hourly_counts[recipient] = recent
                else:
                    empty_recipients.append(recipient)
            for r in empty_recipients:
                del self._recipient_hourly_counts[r]
                purged += 1

            # Clean up idempotency keys older than 24h
            expired_keys = [k for k, ts in self._sent_idempotency_keys.items() if ts < one_day_ago]
            for k in expired_keys:
                del self._sent_idempotency_keys[k]
                purged += 1

        return purged

    async def _record_dispatch(self, idempotency_key: str, recipient: str, record: NotificationRecord):
        now = time.time()
        async with self._lock:
            self._sent_idempotency_keys[idempotency_key] = now
            if recipient not in self._recipient_hourly_counts:
                self._recipient_hourly_counts[recipient] = []
            self._recipient_hourly_counts[recipient].append(now)
            self._audit_records.append(record)

    def _format_message_for_channel(self, alert: DisasterAlert, channel: NotificationChannel, language: str) -> str:
        if channel == NotificationChannel.WHATSAPP:
            return format_whatsapp_alert(alert, language=language)
        elif channel == NotificationChannel.SMS:
            return format_sms_alert(alert, language=language)
        elif channel == NotificationChannel.VOICE_IVR:
            return format_voice_script(alert, language=language)
        return alert.headline or alert.title

    async def _dispatch_to_adapter(self, channel: NotificationChannel, payload: NotificationPayload):
        if channel == NotificationChannel.WHATSAPP:
            provider = settings.WHATSAPP_PROVIDER.lower()
            if provider == "twilio":
                return await twilio_whatsapp_adapter.send_notification(payload)
            elif provider in ["baileys", "live_baileys"]:
                return await baileys_whatsapp_adapter.send_notification(payload)
            return await whatsapp_notification_adapter.send_notification(payload)
        elif channel == NotificationChannel.SMS:
            if settings.SMS_PROVIDER.lower() == "exotel":
                return await exotel_sms_adapter.send_notification(payload)
            return await textbee_sms_adapter.send_notification(payload)
        elif channel == NotificationChannel.VOICE_IVR:
            if settings.VOICE_PROVIDER.lower() == "twilio":
                return await twilio_voice_adapter.send_notification(payload)
            return await exotel_voice_adapter.send_notification(payload)
        elif channel == NotificationChannel.WEB_PUSH:
            return await web_push_adapter.send_notification(payload)
        return await web_push_adapter.send_notification(payload)

    def _get_provider_name(self, channel: NotificationChannel) -> str:
        if channel == NotificationChannel.WHATSAPP:
            provider = settings.WHATSAPP_PROVIDER.lower()
            if provider == "twilio":
                return "Twilio WhatsApp"
            elif provider in ["baileys", "live_baileys"]:
                return "Baileys WhatsApp"
            return "Meta WhatsApp Cloud API"
        elif channel == NotificationChannel.SMS:
            return "Exotel SMS" if settings.SMS_PROVIDER.lower() == "exotel" else "TextBee SMS"
        elif channel == NotificationChannel.VOICE_IVR:
            return "Twilio Voice / IVR" if settings.VOICE_PROVIDER.lower() == "twilio" else "Exotel Voice / IVR"
        elif channel == NotificationChannel.WEB_PUSH:
            return "VAPID Web Push"
        return "Web Push"

    def preview_message(self, alert: DisasterAlert, channel: NotificationChannel, language: str, recipient: str) -> NotificationPreviewResponse:
        """Simulates and previews rendered notification format across channels and languages."""
        formatted = self._format_message_for_channel(alert, channel, language)
        return NotificationPreviewResponse(
            channel=channel,
            language=language,
            recipient=mask_phone_number(recipient) or recipient,
            formatted_message=formatted,
            provider=self._get_provider_name(channel),
            dry_run=True, # Previews are ALWAYS strictly simulated
            metadata={
                "alert_id": alert.alert_id,
                "event_type": alert.event_type,
                "severity": alert.severity.value,
                "scope": alert.scope.value
            }
        )

    async def send_test_notification(
        self,
        user_identifier: str,
        channel: NotificationChannel
    ) -> NotificationRecord:
        """
        Phase 1 Isolated Test Notification Action.
        Sends a test message ONLY to the currently registered user's own configured destination.
        - Does NOT invoke Gemini.
        - Does NOT invoke SACHET or GDACS.
        - Does NOT enter the real emergency-alert pipeline.
        - Active in Phase 1 ONLY for WHATSAPP and WEB_PUSH.
        """
        # Phase 2 Guard: Voice/IVR remains Phase 3
        if channel == NotificationChannel.VOICE_IVR:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel '{channel.value}' is not active in Phase 2. Voice/IVR remains Phase 3."
            )

        # 1. Fetch user subscription from Supabase to retrieve destination
        sub = await self.get_subscription(user_identifier)
        if not sub or not sub.is_opted_in:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active subscription found for user '{user_identifier}'. Please save preferences first."
            )

        if channel not in sub.enabled_channels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel '{channel.value}' is not enabled in user preferences."
            )

        recipient = None
        if channel == NotificationChannel.WHATSAPP:
            recipient = sub.whatsapp_number or sub.phone_number
        elif channel == NotificationChannel.SMS:
            recipient = sub.phone_number
        elif channel == NotificationChannel.WEB_PUSH:
            recipient = sub.user_identifier


        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No recipient details configured for channel '{channel.value}'."
            )

        # Generate unique test idempotency key per manual request (no artificial suppression)
        idempotency_key = f"test:{user_identifier}:{channel.value}:{uuid.uuid4().hex[:8]}"

        # Fixed mandatory Phase 1 test message
        test_message = "You have subscribed to WeatherGPT.\nThis is a test message you triggered."

        payload = NotificationPayload(
            recipient_identifier=recipient,
            channel=channel,
            title="WeatherGPT Test Notification",
            message=test_message,
            priority="high",
            alert_id="TEST-NOTIFICATION",
            language=sub.preferred_language,
            push_subscription=sub.push_subscription if channel == NotificationChannel.WEB_PUSH else None
        )

        try:
            delivery_status = await self._dispatch_to_adapter(channel, payload)
        except Exception as e:
            logger.error(f"Provider adapter error on test channel {channel.value}: {str(e)}")
            delivery_status = None

        record = NotificationRecord(
            notification_id=delivery_status.notification_id if delivery_status else str(uuid.uuid4()),
            alert_id="TEST-NOTIFICATION",
            channel=channel,
            recipient=mask_phone_number(recipient) or recipient,
            status=delivery_status.status if delivery_status else NotificationStatus.FAILED,
            provider=self._get_provider_name(channel),
            sent_at=datetime.utcnow() if delivery_status and delivery_status.status in [NotificationStatus.SENT, NotificationStatus.SIMULATED] else None,
            failed_at=datetime.utcnow() if not delivery_status or delivery_status.status == NotificationStatus.FAILED else None,
            provider_message_id=delivery_status.provider_reference if delivery_status else None,
            error_message=delivery_status.error_message if delivery_status else "Unhandled adapter exception",
            idempotency_key=idempotency_key,
            dry_run=delivery_status.is_simulated if delivery_status else settings.NOTIFICATION_DRY_RUN
        )

        await self._record_dispatch(idempotency_key, recipient, record)
        return record

notification_orchestrator = NotificationOrchestrator()

