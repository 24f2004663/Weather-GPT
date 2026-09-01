import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set, Tuple, Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from backend.core.config import settings
from backend.core.logging import logger

@dataclass
class GeminiModelConfig:
    name: str
    display_name: str
    priority: int
    safe_rpm: int
    safe_rpd: int
    safe_tpm: int

def get_pacific_date_str() -> str:
    """
    Returns current date string (YYYY-MM-DD) in US/Pacific timezone.
    Google AI Studio resets daily request limits at midnight Pacific Time.
    """
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
        except Exception:
            pass
    # Fallback UTC-7 approximation for US Pacific (PDT) / UTC-8 (PST)
    return (datetime.now(timezone.utc) - timedelta(hours=7)).strftime("%Y-%m-%d")

class GeminiModelRouter:
    """
    Concurrency-safe, quota-aware multi-model Gemini router.
    
    Guarantees:
    - 1 Actual Gemini HTTP POST = 1 RPM Reservation = 1 RPD Count.
    - Zero permanent downgrade: every HTTP request starts evaluating from Model #1.
    - Continuous rolling 60-second sliding RPM window.
    - Midnight US/Pacific daily RPD reset tracking.
    - In-flight concurrency safety via asyncio.Lock.
    - Temporary model suppression and automatic cascade fallback on HTTP 429.
    """
    def __init__(self):
        self._lock = asyncio.Lock()
        self._models: List[GeminiModelConfig] = self._build_model_registry()
        
        # State tracking per model
        self._rpm_timestamps: Dict[str, List[float]] = {m.name: [] for m in self._models}
        self._tpm_records: Dict[str, List[Tuple[float, int]]] = {m.name: [] for m in self._models}
        self._rpd_counts: Dict[str, int] = {m.name: 0 for m in self._models}
        self._rpd_date: str = get_pacific_date_str()
        self._suppressed_until: Dict[str, float] = {m.name: 0.0 for m in self._models}

    def _build_model_registry(self) -> List[GeminiModelConfig]:
        """Loads model registry in strict priority order from configuration."""
        return [
            GeminiModelConfig(
                name=settings.GEMINI_MODEL_1,
                display_name="Gemini 3.5 Flash Lite",
                priority=1,
                safe_rpm=settings.GEMINI_FLASH_LITE_SAFE_RPM,
                safe_rpd=settings.GEMINI_FLASH_LITE_SAFE_RPD,
                safe_tpm=settings.GEMINI_FLASH_LITE_SAFE_TPM,
            ),
            GeminiModelConfig(
                name=settings.GEMINI_MODEL_2,
                display_name="Gemini 3.1 Flash Lite",
                priority=2,
                safe_rpm=settings.GEMINI_FLASH_LITE_31B_SAFE_RPM,
                safe_rpd=settings.GEMINI_FLASH_LITE_31B_SAFE_RPD,
                safe_tpm=settings.GEMINI_FLASH_LITE_31B_SAFE_TPM,
            ),
            GeminiModelConfig(
                name=settings.GEMINI_MODEL_3,
                display_name="Gemma 4 31B",
                priority=3,
                safe_rpm=settings.GEMMA_4_31B_SAFE_RPM,
                safe_rpd=settings.GEMMA_4_31B_SAFE_RPD,
                safe_tpm=settings.GEMMA_4_31B_SAFE_TPM,
            ),
            GeminiModelConfig(
                name=settings.GEMINI_MODEL_4,
                display_name="Gemma 4 26B",
                priority=4,
                safe_rpm=settings.GEMMA_4_26B_SAFE_RPM,
                safe_rpd=settings.GEMMA_4_26B_SAFE_RPD,
                safe_tpm=settings.GEMMA_4_26B_SAFE_TPM,
            ),
        ]

    def reload_registry(self):
        """Re-initializes model registry from settings if configuration changes."""
        self._models = self._build_model_registry()
        for m in self._models:
            if m.name not in self._rpm_timestamps:
                self._rpm_timestamps[m.name] = []
                self._tpm_records[m.name] = []
                self._rpd_counts[m.name] = 0
                self._suppressed_until[m.name] = 0.0

    def _prune_state(self, now: float):
        """Prunes sliding 60s windows and checks Pacific midnight rollover."""
        current_date = get_pacific_date_str()
        if current_date != self._rpd_date:
            logger.info(f"[Gemini Router] Pacific midnight rollover ({self._rpd_date} -> {current_date}). Resetting daily RPD counters.")
            for m in self._models:
                self._rpd_counts[m.name] = 0
            self._rpd_date = current_date

        cutoff = now - 60.0
        for m in self._models:
            self._rpm_timestamps[m.name] = [t for t in self._rpm_timestamps[m.name] if t > cutoff]
            self._tpm_records[m.name] = [r for r in self._tpm_records[m.name] if r[0] > cutoff]

    async def select_and_reserve_model(
        self,
        excluded_models: Optional[Set[str]] = None,
        estimated_tokens: int = 1000
    ) -> Optional[Tuple[GeminiModelConfig, str]]:
        """
        Atomically selects the highest-priority eligible model and reserves quota
        for ONE upcoming outbound Gemini HTTP request.
        Always evaluates models in strict priority order (1 -> 2 -> 3 -> 4).
        """
        excluded = excluded_models or set()
        now = time.time()

        async with self._lock:
            self._prune_state(now)

            skipped_reasons = []

            for model in self._models:
                # 1. Skip explicitly excluded models for this attempt
                if model.name in excluded:
                    skipped_reasons.append(f"{model.name}:excluded")
                    continue

                # 2. Check temporary 429 suppression
                if self._suppressed_until.get(model.name, 0.0) > now:
                    remaining_suppress = int(self._suppressed_until[model.name] - now)
                    skipped_reasons.append(f"{model.name}:429_suppressed({remaining_suppress}s)")
                    continue

                # 3. Check rolling 60s RPM
                current_rpm = len(self._rpm_timestamps[model.name])
                if current_rpm >= model.safe_rpm:
                    skipped_reasons.append(f"{model.name}:rpm_limit({current_rpm}/{model.safe_rpm})")
                    continue

                # 4. Check Pacific daily RPD
                current_rpd = self._rpd_counts.get(model.name, 0)
                if current_rpd >= model.safe_rpd:
                    skipped_reasons.append(f"{model.name}:rpd_limit({current_rpd}/{model.safe_rpd})")
                    continue

                # 5. Check rolling 60s TPM
                current_tpm = sum(tok for _, tok in self._tpm_records[model.name])
                if current_tpm + estimated_tokens > model.safe_tpm:
                    skipped_reasons.append(f"{model.name}:tpm_limit({current_tpm}/{model.safe_tpm})")
                    continue

                # Model is eligible! Reserve slot atomically for this HTTP request
                self._rpm_timestamps[model.name].append(now)
                self._tpm_records[model.name].append((now, estimated_tokens))
                self._rpd_counts[model.name] = current_rpd + 1

                new_rpm = len(self._rpm_timestamps[model.name])
                new_rpd = self._rpd_counts[model.name]

                # Determine structured reason
                if model.priority == 1:
                    reason = "primary_available"
                elif model.priority == 2:
                    reason = "primary_rpm_threshold" if "gemini-3.5-flash-lite:rpm_limit" in ",".join(skipped_reasons) else "primary_unavailable"
                elif model.priority == 3:
                    reason = "primary_secondary_unavailable"
                else:
                    reason = "all_higher_priority_models_unavailable"

                logger.info(
                    f"[Gemini Router] event=reserve model={model.name} "
                    f"rpm={new_rpm}/{model.safe_rpm} rpd={new_rpd}/{model.safe_rpd} reason={reason}"
                )
                return model, reason

            logger.warning(f"[Gemini Router] all_models_unavailable. Details: {', '.join(skipped_reasons)}")
            return None

    async def record_429(self, model_name: str):
        """
        Marks model as temporarily suppressed after upstream 429 response.
        The slot reservation already occurred before dispatch, so request accounting is preserved.
        """
        now = time.time()
        suppress_duration = settings.GEMINI_429_SUPPRESS_SECONDS
        async with self._lock:
            self._suppressed_until[model_name] = now + suppress_duration
            logger.warning(f"[Gemini Router] model={model_name} event=429 action=temporary_suppress (suppressed for {suppress_duration}s)")

    async def record_release(self, model_name: str, estimated_tokens: int = 1000):
        """
        Releases reserved slot if a local error aborted before external HTTP dispatch.
        """
        async with self._lock:
            if model_name in self._rpm_timestamps and self._rpm_timestamps[model_name]:
                self._rpm_timestamps[model_name].pop()
            if model_name in self._tpm_records and self._tpm_records[model_name]:
                self._tpm_records[model_name].pop()
            if model_name in self._rpd_counts and self._rpd_counts[model_name] > 0:
                self._rpd_counts[model_name] -= 1

    async def reset_state(self):
        """Resets all tracking state for test isolation."""
        async with self._lock:
            for m in self._models:
                self._rpm_timestamps[m.name] = []
                self._tpm_records[m.name] = []
                self._rpd_counts[m.name] = 0
                self._suppressed_until[m.name] = 0.0
            self._rpd_date = get_pacific_date_str()

    async def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic status of all models in registry."""
        now = time.time()
        async with self._lock:
            self._prune_state(now)
            status = {}
            for m in self._models:
                suppress_left = max(0, int(self._suppressed_until.get(m.name, 0.0) - now))
                status[m.name] = {
                    "priority": m.priority,
                    "display_name": m.display_name,
                    "current_rpm": len(self._rpm_timestamps[m.name]),
                    "safe_rpm": m.safe_rpm,
                    "current_rpd": self._rpd_counts.get(m.name, 0),
                    "safe_rpd": m.safe_rpd,
                    "current_tpm": sum(tok for _, tok in self._tpm_records[m.name]),
                    "safe_tpm": m.safe_tpm,
                    "is_429_suppressed": suppress_left > 0,
                    "suppress_seconds_remaining": suppress_left,
                }
            return status

gemini_model_router = GeminiModelRouter()
