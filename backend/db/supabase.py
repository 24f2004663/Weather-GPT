from typing import Dict, Any, Optional
from backend.core.config import settings
from backend.core.logging import logger

class SupabaseClient:
    """
    Safe Supabase Database & Auth Adapter.
    Manages connection metadata without exposing raw secrets.
    """
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.has_credentials = bool(self.url and (settings.SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_ROLE_KEY))

    def is_configured(self) -> bool:
        return self.has_credentials

    async def check_connection(self) -> bool:
        if not self.has_credentials:
            logger.info("Supabase not fully configured; operating in local decoupled mode for Phase 1.")
            return False
        return True

db_client = SupabaseClient()
