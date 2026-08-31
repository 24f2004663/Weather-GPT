import asyncio
import time
import uuid
from typing import Dict, List, Optional, Tuple, Any
from backend.schemas.chat import ChatMessage
from backend.core.errors import WeatherGPTError

class InvalidSessionRoleError(WeatherGPTError):
    pass

class SessionStore:
    """
    Thread-safe and async-compatible in-memory conversational session store with TTL and capacity limits.
    Prevents unbounded memory growth and ensures strict message hygiene.
    """
    def __init__(
        self,
        max_messages_per_session: int = 20,
        session_ttl_seconds: int = 3600,
        max_message_chars: int = 4000
    ):
        self._sessions: Dict[str, Tuple[List[ChatMessage], float]] = {}
        self._max_messages = max_messages_per_session
        self._ttl_seconds = session_ttl_seconds
        self._max_message_chars = max_message_chars
        self._lock = asyncio.Lock()

    async def get_or_create_session(self, session_id: Optional[str] = None) -> Tuple[str, List[ChatMessage]]:
        """
        Retrieves active unexpired messages for session_id or creates a new session.
        """
        async with self._lock:
            now = time.time()
            sid = session_id.strip() if session_id and session_id.strip() else str(uuid.uuid4())

            if sid in self._sessions:
                messages, expires_at = self._sessions[sid]
                if now > expires_at:
                    # Expired session -> reset history
                    messages = []
                # Refresh TTL on access
                self._sessions[sid] = (messages, now + self._ttl_seconds)
                return sid, [ChatMessage(**m.dict()) for m in messages]

            # New session
            self._sessions[sid] = ([], now + self._ttl_seconds)
            return sid, []

    async def append_messages(self, session_id: str, new_messages: List[ChatMessage]) -> None:
        """
        Appends new validated messages to the session, enforcing role validation and history limits.
        """
        valid_roles = {"user", "assistant", "system"}
        sanitized_messages: List[ChatMessage] = []

        for msg in new_messages:
            if msg.role not in valid_roles:
                raise InvalidSessionRoleError(f"Invalid message role '{msg.role}'. Allowed roles: {valid_roles}")

            # Truncate oversized message content to bounded length
            content = msg.content
            if len(content) > self._max_message_chars:
                content = content[:self._max_message_chars] + " ...[truncated]"

            sanitized_messages.append(
                ChatMessage(
                    role=msg.role,
                    content=content,
                    timestamp=msg.timestamp,
                    source_attribution=msg.source_attribution
                )
            )

        async with self._lock:
            now = time.time()
            current_list = []
            if session_id in self._sessions:
                existing_msgs, _ = self._sessions[session_id]
                current_list = list(existing_msgs)

            current_list.extend(sanitized_messages)

            # Cap message history to prevent unbounded growth
            if len(current_list) > self._max_messages:
                current_list = current_list[-self._max_messages:]

            self._sessions[session_id] = (current_list, now + self._ttl_seconds)

    async def clear_session(self, session_id: str) -> bool:
        """Explicitly deletes a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def cleanup_expired(self) -> int:
        """Purges expired sessions from memory."""
        now = time.time()
        purged = 0
        async with self._lock:
            expired_keys = [sid for sid, (_, exp) in self._sessions.items() if now > exp]
            for sid in expired_keys:
                del self._sessions[sid]
                purged += 1
        return purged

    def active_sessions_count(self) -> int:
        return len(self._sessions)

session_store = SessionStore()
