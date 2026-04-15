"""Claude-powered conversation engine for the voice assistant.

Manages per-call conversation history and generates AI responses
using the Anthropic API.  Each active call gets its own message
history keyed by Twilio CallSid.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

from anthropic import Anthropic

from voice_assistant.config import AnthropicConfig, VoiceAssistantConfig
from voice_assistant.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session storage
# ---------------------------------------------------------------------------

@dataclass
class CallSession:
    """State for a single active phone call."""

    call_sid: str
    caller_number: str
    messages: list[dict] = field(default_factory=list)
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)
    transfer_requested: bool = False
    collected_info: dict = field(default_factory=dict)


class SessionStore:
    """Thread-safe in-memory store for active call sessions."""

    def __init__(self):
        self._sessions: dict[str, CallSession] = {}
        self._lock = threading.Lock()

    def create(self, call_sid: str, caller_number: str) -> CallSession:
        session = CallSession(call_sid=call_sid, caller_number=caller_number)
        with self._lock:
            self._sessions[call_sid] = session
        logger.info("Session created: %s from %s", call_sid, caller_number)
        return session

    def get(self, call_sid: str) -> CallSession | None:
        with self._lock:
            return self._sessions.get(call_sid)

    def remove(self, call_sid: str) -> CallSession | None:
        with self._lock:
            return self._sessions.pop(call_sid, None)

    def all_sessions(self) -> list[CallSession]:
        with self._lock:
            return list(self._sessions.values())


# Module-level store shared across the application
sessions = SessionStore()

# ---------------------------------------------------------------------------
# Conversation engine
# ---------------------------------------------------------------------------

class ConversationEngine:
    """Generates voice assistant responses using Claude."""

    def __init__(self):
        self.client = Anthropic(api_key=AnthropicConfig.API_KEY)
        self.system_prompt = build_system_prompt()
        self.model = AnthropicConfig.MODEL
        self.max_tokens = AnthropicConfig.MAX_TOKENS
        self.temperature = AnthropicConfig.TEMPERATURE

    def respond(self, call_sid: str, caller_speech: str) -> str:
        """Generate an assistant response for the given call.

        Args:
            call_sid: The Twilio CallSid identifying the call.
            caller_speech: The transcribed text of what the caller said.

        Returns:
            The assistant's text response to be spoken via TTS.
        """
        session = sessions.get(call_sid)
        if session is None:
            logger.error("No session for call %s", call_sid)
            return (
                "I'm sorry, I seem to have lost our conversation. "
                "Could you please call back? I apologize for the inconvenience."
            )

        # Append the caller's message
        session.messages.append({"role": "user", "content": caller_speech})
        session.turn_count += 1

        # Check if we've exceeded the max turns — suggest transfer
        if session.turn_count >= VoiceAssistantConfig.MAX_TURNS:
            transfer_msg = (
                "I want to make sure you get the help you need. "
                "Let me transfer you to a team member. Please hold."
            )
            session.messages.append({"role": "assistant", "content": transfer_msg})
            session.transfer_requested = True
            return transfer_msg

        # Call Claude API
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                messages=session.messages,
            )
            assistant_text = response.content[0].text
        except Exception:
            logger.exception("Claude API error for call %s", call_sid)
            assistant_text = (
                "I'm sorry, I'm having a little trouble right now. "
                "Could you please repeat that?"
            )

        # Record the assistant response in history
        session.messages.append({"role": "assistant", "content": assistant_text})

        # Detect transfer marker
        if "[TRANSFER_TO_STAFF]" in assistant_text:
            session.transfer_requested = True
            # Strip the marker — it shouldn't be spoken aloud
            assistant_text = assistant_text.replace("[TRANSFER_TO_STAFF]", "").strip()

        logger.info(
            "Call %s turn %d — caller: %.80s... → assistant: %.80s...",
            call_sid,
            session.turn_count,
            caller_speech,
            assistant_text,
        )
        return assistant_text

    def build_call_summary(self, call_sid: str) -> str:
        """Build a human-readable summary of the call for the care team.

        Args:
            call_sid: The Twilio CallSid.

        Returns:
            A formatted text summary of the conversation.
        """
        session = sessions.get(call_sid)
        if session is None:
            return f"No session data for call {call_sid}."

        try:
            summary_response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.0,
                system=(
                    "You are a clinical note summarizer. Summarize the following "
                    "phone conversation between a patient caller and the virtual "
                    "assistant. Include: caller's name (if given), date of birth "
                    "(if given), reason for call, any details collected (appointment "
                    "preferences, medications, messages), and any follow-up actions "
                    "needed by staff. Keep it concise and professional."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": _format_transcript(session),
                    }
                ],
            )
            return summary_response.content[0].text
        except Exception:
            logger.exception("Failed to summarize call %s", call_sid)
            return _format_transcript(session)


def _format_transcript(session: CallSession) -> str:
    """Format the raw conversation history as a readable transcript."""
    lines = [
        f"Call from: {session.caller_number}",
        f"Turns: {session.turn_count}",
        "---",
    ]
    for msg in session.messages:
        role = "Caller" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)
