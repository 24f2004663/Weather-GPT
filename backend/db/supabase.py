import re
import json
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from backend.core.config import settings
from backend.core.logging import logger
from backend.schemas.notifications import NotificationSubscription, NotificationChannel
from backend.schemas.alerts import AlertSeverity

class SupabaseClient:
    """
    Authoritative Supabase Database & REST Adapter for Emergency Alert Subscriptions.
    Communicates securely with Supabase PostgREST (public.alert_subscriptions) without exposing raw secrets.
    """
    def __init__(self):
        self.url = (settings.SUPABASE_URL or "").rstrip("/")
        self.key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
        self.has_credentials = bool(
            self.url and self.key and not self.url.endswith("supabase.co_supabase_project_url")
        )
        self._table = "alert_subscriptions"

    def is_configured(self) -> bool:
        return self.has_credentials

    def _get_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key or "",
            "Authorization": f"Bearer {self.key or ''}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def save_subscription(self, sub: NotificationSubscription) -> bool:
        """
        Persists or updates an Emergency Alert subscription in Supabase (public.alert_subscriptions).
        Returns True ONLY if the database write succeeded.
        """
        if not self.has_credentials:
            logger.error("SupabaseClient.save_subscription called but Supabase credentials are not configured.")
            return False

        payload = {
            "subscription_id": sub.subscription_id,
            "user_identifier": sub.user_identifier,
            "phone_number": sub.phone_number,
            "whatsapp_number": sub.whatsapp_number,
            "preferred_language": sub.preferred_language,
            "enabled_channels": [
                c.value if hasattr(c, "value") else str(c) for c in sub.enabled_channels
            ],
            "min_severity_threshold": (
                sub.min_severity_threshold.value
                if hasattr(sub.min_severity_threshold, "value")
                else str(sub.min_severity_threshold)
            ),
            "target_states": sub.target_states,
            "target_districts": sub.target_districts,
            "push_subscription": sub.push_subscription,
            "is_opted_in": sub.is_opted_in,
            "updated_at": datetime.utcnow().isoformat(),
        }

        endpoint = f"{self.url}/rest/v1/{self._table}?on_conflict=user_identifier"
        headers = self._get_headers(prefer="resolution=merge-duplicates,return=representation")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(endpoint, headers=headers, json=payload)
                if res.status_code in (200, 201, 204):
                    logger.info(f"Supabase successfully persisted subscription for: {sub.user_identifier}")
                    return True
                logger.error(f"Supabase upsert failed with HTTP {res.status_code}: {res.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Supabase save_subscription network/connection error: {str(e)}")
            return False

    async def get_subscription(self, user_identifier: str) -> Optional[NotificationSubscription]:
        """
        Retrieves a user's subscription record directly from Supabase.
        """
        if not self.has_credentials:
            return None

        endpoint = f"{self.url}/rest/v1/{self._table}"
        params = {
            "user_identifier": f"eq.{user_identifier}",
            "select": "*",
            "limit": "1",
        }
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(endpoint, headers=headers, params=params)
                if res.status_code == 200:
                    rows = res.json()
                    if rows and len(rows) > 0:
                        row = rows[0]
                        return self._row_to_subscription(row)
                return None
        except Exception as e:
            logger.error(f"Supabase get_subscription error: {str(e)}")
            return None

    async def delete_subscription(self, user_identifier: str) -> bool:
        """
        Removes a subscription record directly from Supabase.
        """
        if not self.has_credentials:
            return False

        endpoint = f"{self.url}/rest/v1/{self._table}"
        params = {"user_identifier": f"eq.{user_identifier}"}
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.delete(endpoint, headers=headers, params=params)
                if res.status_code in (200, 204):
                    logger.info(f"Supabase subscription deleted for: {user_identifier}")
                    return True
                logger.error(f"Supabase delete_subscription failed HTTP {res.status_code}")
                return False
        except Exception as e:
            logger.error(f"Supabase delete_subscription error: {str(e)}")
            return False

    async def is_phone_subscribed(self, phone: str) -> bool:
        """
        Performs an authoritative live query against Supabase to verify if a phone number
        belongs to an active, opted-in Emergency Alert subscriber.
        Returns True if verified active in Supabase, False otherwise.
        """
        if not self.has_credentials:
            return False

        clean_target = "".join(c for c in phone if c.isdigit())
        if not clean_target:
            return False

        endpoint = f"{self.url}/rest/v1/{self._table}"
        params = {
            "is_opted_in": "eq.true",
            "select": "user_identifier,phone_number,whatsapp_number,is_opted_in",
        }
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(endpoint, headers=headers, params=params)
                if res.status_code == 200:
                    rows = res.json()
                    for r in rows:
                        candidate_phones = [
                            r.get("phone_number"),
                            r.get("whatsapp_number"),
                            r.get("user_identifier"),
                        ]
                        for cp in candidate_phones:
                            if not cp:
                                continue
                            clean_cp = "".join(c for c in str(cp) if c.isdigit())
                            if clean_cp == clean_target:
                                return True
                            if len(clean_cp) >= 10 and len(clean_target) >= 10 and clean_cp[-10:] == clean_target[-10:]:
                                return True
                    return False
                logger.warning(f"Supabase is_phone_subscribed HTTP {res.status_code}")
                return False
        except Exception as e:
            logger.error(f"Supabase is_phone_subscribed query error: {str(e)}")
            return False

    async def get_all_active_subscriptions(self) -> List[NotificationSubscription]:
        """
        Retrieves all active (is_opted_in=true) subscriptions directly from Supabase.
        """
        if not self.has_credentials:
            return []

        endpoint = f"{self.url}/rest/v1/{self._table}"
        params = {
            "is_opted_in": "eq.true",
            "select": "*",
        }
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(endpoint, headers=headers, params=params)
                if res.status_code == 200:
                    rows = res.json()
                    return [self._row_to_subscription(r) for r in rows]
                logger.warning(f"Supabase get_all_active_subscriptions HTTP {res.status_code}")
                return []
        except Exception as e:
            logger.error(f"Supabase get_all_active_subscriptions error: {str(e)}")
            return []

    def _row_to_subscription(self, row: Dict[str, Any]) -> NotificationSubscription:
        channels = []
        for ch in row.get("enabled_channels") or []:
            try:
                channels.append(NotificationChannel(ch))
            except ValueError:
                pass

        try:
            severity = AlertSeverity(row.get("min_severity_threshold", "Severe"))
        except ValueError:
            severity = AlertSeverity.SEVERE

        return NotificationSubscription(
            subscription_id=str(row.get("subscription_id")),
            user_identifier=str(row.get("user_identifier")),
            phone_number=row.get("phone_number"),
            whatsapp_number=row.get("whatsapp_number"),
            preferred_language=row.get("preferred_language", "en"),
            enabled_channels=channels,
            min_severity_threshold=severity,
            target_states=row.get("target_states") or [],
            target_districts=row.get("target_districts") or [],
            push_subscription=row.get("push_subscription"),
            is_opted_in=bool(row.get("is_opted_in", True)),
        )

    async def has_seen_alert(self, alert_id: str) -> Tuple[bool, Optional[str]]:
        """
        Checks if an alert ID has been seen in Supabase.
        Returns (has_seen, previous_severity).
        """
        if not self.has_credentials:
            return False, None

        endpoint = f"{self.url}/rest/v1/seen_alerts"
        params = {"alert_id": f"eq.{alert_id}", "select": "alert_id,severity,is_active"}
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(endpoint, headers=headers, params=params)
                if res.status_code == 200:
                    rows = res.json()
                    if rows:
                        return True, rows[0].get("severity")
                return False, None
        except Exception as e:
            logger.error(f"Supabase has_seen_alert query error: {str(e)}")
            return False, None

    async def mark_alert_seen(self, alert_id: str, source: str, severity: str, is_active: bool = True) -> bool:
        """
        Records or updates an alert in seen_alerts.
        """
        if not self.has_credentials:
            return False

        payload = {
            "alert_id": alert_id,
            "source": source,
            "severity": severity,
            "is_active": is_active,
            "last_seen_at": datetime.utcnow().isoformat(),
        }
        endpoint = f"{self.url}/rest/v1/seen_alerts?on_conflict=alert_id"
        headers = self._get_headers(prefer="resolution=merge-duplicates")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(endpoint, headers=headers, json=payload)
                return res.status_code in (200, 201, 204)
        except Exception as e:
            logger.error(f"Supabase mark_alert_seen error: {str(e)}")
            return False

    async def mark_alert_inactive(self, alert_id: str) -> bool:
        """
        Marks an alert as inactive in seen_alerts.
        """
        if not self.has_credentials:
            return False

        endpoint = f"{self.url}/rest/v1/seen_alerts"
        params = {"alert_id": f"eq.{alert_id}"}
        headers = self._get_headers()
        payload = {"is_active": False, "last_seen_at": datetime.utcnow().isoformat()}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.patch(endpoint, headers=headers, params=params, json=payload)
                return res.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Supabase mark_alert_inactive error: {str(e)}")
            return False

supabase_client = SupabaseClient()

