import re
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from backend.schemas.alerts import DisasterAlert, AlertSeverity

PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")
USER_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\@]{3,64}$")

def normalize_phone_number(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    cleaned = re.sub(r"[\s\-\(\)]", "", val.strip())
    if not PHONE_REGEX.match(cleaned):
        raise ValueError(f"Invalid phone number format '{val}'. Must match E.164 specification (e.g. +919876543210).")
    return cleaned

def mask_phone_number(phone: Optional[str]) -> Optional[str]:
    if not phone or len(phone) < 6:
        return phone
    return phone[:3] + " " + phone[3:7] + " ****" + phone[-2:]

class NotificationChannel(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    VOICE_IVR = "VOICE_IVR"
    WEB_PUSH = "WEB_PUSH"

class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    SIMULATED = "SIMULATED"

class NotificationPayload(BaseModel):
    recipient_identifier: str = Field(..., description="Phone number or push subscription ID")
    channel: NotificationChannel
    title: str
    message: str
    template_id: Optional[str] = None
    template_params: Optional[Dict[str, str]] = None
    priority: str = "high"
    alert_id: Optional[str] = None
    language: str = "en"
    push_subscription: Optional[Dict[str, Any]] = None

class DeliveryStatus(BaseModel):
    notification_id: str
    channel: NotificationChannel
    recipient: str
    status: NotificationStatus
    provider_reference: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    is_simulated: bool = False

class DisasterAlertTriggeredEvent(BaseModel):
    event_id: str
    alert: DisasterAlert
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    target_regions: List[str] = []
    eligible_channels: List[NotificationChannel] = [
        NotificationChannel.WEB_PUSH,
        NotificationChannel.WHATSAPP,
        NotificationChannel.SMS,
        NotificationChannel.VOICE_IVR
    ]

class NotificationRecord(BaseModel):
    notification_id: str
    alert_id: str
    channel: NotificationChannel
    recipient: str
    status: NotificationStatus
    provider: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    retry_count: int = 0
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    idempotency_key: str
    dry_run: bool = True

class NotificationSubscription(BaseModel):
    subscription_id: str
    user_identifier: str = Field(..., description="User or browser client token")
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    preferred_language: str = "en"
    enabled_channels: List[NotificationChannel] = [NotificationChannel.WEB_PUSH]
    min_severity_threshold: AlertSeverity = AlertSeverity.SEVERE
    target_states: List[str] = []
    target_districts: List[str] = []
    push_subscription: Optional[Dict[str, Any]] = None
    is_opted_in: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @validator("phone_number", pre=True)
    def validate_phone(cls, v):
        return normalize_phone_number(v)

    @validator("whatsapp_number", pre=True)
    def validate_whatsapp(cls, v):
        return normalize_phone_number(v)

    @validator("user_identifier")
    def validate_user_id(cls, v):
        if not USER_ID_REGEX.match(v):
            raise ValueError(f"Invalid user_identifier '{v}'. Must be 3-64 alphanumeric characters.")
        return v

class SubscriptionRequest(BaseModel):
    user_identifier: str
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    preferred_language: str = "en"
    enabled_channels: List[NotificationChannel] = [NotificationChannel.WEB_PUSH]
    min_severity_threshold: AlertSeverity = AlertSeverity.SEVERE
    target_states: List[str] = []
    target_districts: List[str] = []
    push_subscription: Optional[Dict[str, Any]] = None
    is_opted_in: bool = True

    @validator("phone_number", pre=True)
    def validate_phone(cls, v):
        return normalize_phone_number(v)

    @validator("whatsapp_number", pre=True)
    def validate_whatsapp(cls, v):
        return normalize_phone_number(v)

    @validator("user_identifier")
    def validate_user_id(cls, v):
        if not USER_ID_REGEX.match(v):
            raise ValueError(f"Invalid user_identifier '{v}'. Must be 3-64 alphanumeric characters.")
        return v

class NotificationPreviewRequest(BaseModel):
    alert_id: Optional[str] = None
    channel: NotificationChannel
    language: str = "en"
    recipient: Optional[str] = "+919876543210"

class NotificationPreviewResponse(BaseModel):
    channel: NotificationChannel
    language: str
    recipient: str
    formatted_message: str
    provider: str
    dry_run: bool
    metadata: Dict[str, Any] = {}

class ProviderStatusResponse(BaseModel):
    channels: Dict[str, str]
    dry_run_enabled: bool
    live_tests_enabled: bool
    subscription_store_mode: str = "in_memory_prototype"
    idempotency_store_mode: str = "in_memory_prototype_24h"
    restart_persistence: bool = False

class VapidPublicKeyResponse(BaseModel):
    public_key: Optional[str] = None
    status: str = Field(..., description="'CONFIGURED' or 'NOT_CONFIGURED'")
    claim_email: str

class TestNotificationRequest(BaseModel):
    user_id: str = Field(..., description="Registered user identifier")
    channel: NotificationChannel = Field(..., description="Channel to trigger test notification for")

