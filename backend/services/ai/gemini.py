import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.http_client import http_client_manager
from backend.core.errors import (
    GeminiConfigMissingError,
    UpstreamProviderError,
    UpstreamTimeoutError,
)
from backend.services.ai.base import BaseAIService
from backend.services.ai.prompts import SYSTEM_INSTRUCTION
from backend.services.ai.tools import GEMINI_WEATHER_TOOLS, execute_weather_tool
from backend.services.ai.session import session_store
from backend.schemas.chat import ChatRequest, ChatResponse, ChatMessage, ToolCallLog

_DEFAULT = object()

class GeminiAIService(BaseAIService):
    """
    Production-grade Google Gemini AI Orchestration Layer.
    Implements structured function calling, bounded tool loops, session history,
    connection pooling, in-turn tool call deduplication, and non-sensitive error boundaries.
    """
    def __init__(
        self,
        api_key: Any = _DEFAULT,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_tool_iterations: int = 5
    ):
        self.api_key = settings.GEMINI_API_KEY if api_key is _DEFAULT else api_key
        self.model = settings.GEMINI_MODEL if model is None else model
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.max_tool_iterations = max_tool_iterations
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate_weather_response(self, request: ChatRequest) -> ChatResponse:
        """
        Executes the conversational AI loop with server-side tool calling and session management.
        """
        if not self.api_key or not self.api_key.strip():
            logger.error("Attempted to call Gemini AI without configured GEMINI_API_KEY")
            raise GeminiConfigMissingError()

        # 1. Manage session state
        session_id, history = await session_store.get_or_create_session(request.session_id)

        # 2. Build conversation contents payload adhering to Gemini API protocol
        contents: List[Dict[str, Any]] = []

        if history:
            # Server-side session store has active history
            for msg in history:
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })
            # Add latest incoming user message
            active_turn_messages = request.messages[-1:] if request.messages else []
        else:
            # Fallback: server session expired or restarted, use client-provided bounded context
            active_turn_messages = request.messages

        for idx, msg in enumerate(active_turn_messages):
            role = "user" if msg.role == "user" else "model"
            # If coordinates or location hint provided on latest user message, inject as non-intrusive metadata header
            if idx == len(active_turn_messages) - 1 and msg.role == "user" and (request.user_location or request.coordinates):
                hints = []
                if request.user_location:
                    hints.append(f"User Location Hint: {request.user_location}")
                if request.coordinates:
                    hints.append(f"Coordinates: lat={request.coordinates.get('latitude')}, lon={request.coordinates.get('longitude')}")
                context_prefix = f"[{', '.join(hints)}]\n" if hints else ""
                contents.append({
                    "role": role,
                    "parts": [{"text": f"{context_prefix}{msg.content}"}]
                })
            else:
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })

        clean_model = (self.model or "gemini-3.5-flash").replace("models/", "")
        endpoint = f"{self.base_url}/models/{clean_model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        sources_used: Set[str] = set()
        tools_used: List[str] = []
        tool_logs: List[ToolCallLog] = []
        referenced_weather_data: Dict[str, Any] = {}
        
        # Single-turn tool deduplication cache (tool_name, frozenset(args)) -> (result, provider)
        turn_tool_cache: Dict[Tuple[str, Tuple], Tuple[Dict[str, Any], str]] = {}

        client = await http_client_manager.get_client()

        # 3. Controlled Tool Calling Execution Loop
        for iteration in range(self.max_tool_iterations):
            body = {
                "contents": contents,
                "systemInstruction": {
                    "parts": [{"text": SYSTEM_INSTRUCTION}]
                },
                "tools": GEMINI_WEATHER_TOOLS,
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1024
                }
            }

            try:
                response = await client.post(endpoint, headers=headers, json=body, timeout=self.timeout)
            except httpx.TimeoutException:
                logger.error(f"Gemini API request timed out after {self.timeout}s on iteration {iteration}")
                raise UpstreamTimeoutError(provider="Gemini API", timeout_seconds=self.timeout)
            except Exception as e:
                logger.error(f"Network error calling Gemini API: {str(e)}")
                raise UpstreamProviderError(provider="Gemini API", status_code=None, message=str(e))

            if response.status_code != 200:
                logger.error(f"Gemini API HTTP {response.status_code}: {response.text[:200]}")
                raise UpstreamProviderError(
                    provider="Gemini API",
                    status_code=response.status_code,
                    message=f"Gemini API returned status {response.status_code}"
                )

            try:
                resp_json = response.json()
            except Exception:
                raise UpstreamProviderError(provider="Gemini API", status_code=200, message="Malformed JSON response from Gemini API")

            candidates = resp_json.get("candidates") or []
            if not candidates:
                prompt_feedback = resp_json.get("promptFeedback", {})
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    raise UpstreamProviderError(
                        provider="Gemini API",
                        status_code=200,
                        message=f"Prompt was blocked by Gemini safety filter: {block_reason}"
                    )
                raise UpstreamProviderError(provider="Gemini API", status_code=200, message="No response candidates returned by Gemini")

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "STOP")

            if finish_reason == "SAFETY":
                safe_reply = ChatMessage(
                    role="assistant",
                    content="I cannot complete this request due to content safety policies.",
                    timestamp=datetime.utcnow(),
                    source_attribution=["Safety Policy"]
                )
                return ChatResponse(
                    response_message=safe_reply,
                    session_id=session_id,
                    referenced_weather_data=None,
                    tools_used=tools_used,
                    tool_execution_logs=tool_logs
                )

            candidate_content = candidate.get("content", {})
            parts = candidate_content.get("parts", [])

            # Extract any functionCall parts
            function_calls = [p["functionCall"] for p in parts if "functionCall" in p]

            if not function_calls:
                # Terminal text response reached
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                assistant_text = "".join(text_parts).strip()

                if not assistant_text:
                    assistant_text = "I've processed your meteorological inquiry based on the retrieved data."

                attributions = sorted(list(sources_used)) if sources_used else ["Gemini AI"]

                response_message = ChatMessage(
                    role="assistant",
                    content=assistant_text,
                    timestamp=datetime.utcnow(),
                    source_attribution=attributions
                )

                # Persist turn into session store
                if request.messages:
                    user_turn = request.messages[-1]
                    await session_store.append_messages(session_id, [user_turn, response_message])

                return ChatResponse(
                    response_message=response_message,
                    session_id=session_id,
                    referenced_weather_data=referenced_weather_data if referenced_weather_data else None,
                    tools_used=tools_used,
                    tool_execution_logs=tool_logs
                )

            # Append model's functionCall turn to contents history
            contents.append({
                "role": "model",
                "parts": parts
            })

            # Execute function calls with in-turn deduplication
            function_response_parts: List[Dict[str, Any]] = []
            for fc in function_calls:
                tool_name = fc.get("name", "")
                raw_args = fc.get("args") or {}
                t_start = time.time()

                tools_used.append(tool_name)
                
                # Normalize arguments for deduplication key
                arg_key = (tool_name, tuple(sorted((k, str(v)) for k, v in raw_args.items())))
                
                if arg_key in turn_tool_cache:
                    tool_result, provider_name = turn_tool_cache[arg_key]
                    logger.debug(f"[Tool DEDUP] Reusing in-turn result for {tool_name}")
                else:
                    tool_result, provider_name = await execute_weather_tool(tool_name, raw_args)
                    turn_tool_cache[arg_key] = (tool_result, provider_name)

                exec_time = (time.time() - t_start) * 1000

                status_flag = tool_result.get("status", "success")
                if status_flag == "success":
                    sources_used.add(provider_name)
                    if "data" in tool_result:
                        referenced_weather_data[tool_name] = tool_result["data"]
                    elif "locations" in tool_result:
                        referenced_weather_data[tool_name] = tool_result["locations"]

                tool_logs.append(ToolCallLog(
                    tool_name=tool_name,
                    arguments=raw_args,
                    status=status_flag,
                    execution_time_ms=exec_time
                ))

                safe_tool_result = json.loads(json.dumps(tool_result, default=str))
                function_response_parts.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": {
                            "name": tool_name,
                            "content": safe_tool_result
                        }
                    }
                })

            contents.append({
                "role": "user",
                "parts": function_response_parts
            })

        attributions = sorted(list(sources_used)) if sources_used else ["Gemini AI"]
        fallback_msg = ChatMessage(
            role="assistant",
            content="I gathered the required weather observations, but reached the processing limit while formulating the final response.",
            timestamp=datetime.utcnow(),
            source_attribution=attributions
        )
        return ChatResponse(
            response_message=fallback_msg,
            session_id=session_id,
            referenced_weather_data=referenced_weather_data if referenced_weather_data else None,
            tools_used=tools_used,
            tool_execution_logs=tool_logs
        )

gemini_ai_service = GeminiAIService()
