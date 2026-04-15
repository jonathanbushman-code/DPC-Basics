"""Logs voice assistant call summaries to Spruce Health.

After each call completes, a summary of the conversation is posted to a
designated Spruce conversation so the care team can review what was
discussed and take any follow-up actions.
"""

import logging
from datetime import datetime, timezone

from clients.spruce_client import SpruceClient
from voice_assistant.config import VoiceAssistantConfig

logger = logging.getLogger(__name__)


class SpruceCallLogger:
    """Posts call summaries to a Spruce conversation for the care team."""

    def __init__(self, spruce_client: SpruceClient | None = None):
        self.spruce = spruce_client or SpruceClient()
        self.conversation_id = (
            VoiceAssistantConfig.SPRUCE_VOICE_LOG_CONVERSATION_ID
        )

    def log_call_summary(
        self,
        caller_number: str,
        call_sid: str,
        summary: str,
        turn_count: int,
        transfer_requested: bool,
    ) -> dict | None:
        """Post a call summary message to the Spruce team conversation.

        Args:
            caller_number: The caller's phone number.
            call_sid: Twilio call identifier.
            summary: AI-generated summary of the conversation.
            turn_count: Number of conversation turns.
            transfer_requested: Whether the caller asked for a live transfer.

        Returns:
            Spruce API response dict, or None if logging is not configured.
        """
        if not self.conversation_id:
            logger.warning(
                "SPRUCE_VOICE_LOG_CONVERSATION_ID not configured — "
                "skipping call log for %s",
                call_sid,
            )
            return None

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        transfer_flag = " [TRANSFER REQUESTED]" if transfer_requested else ""

        message = (
            f"Phone Call Summary{transfer_flag}\n"
            f"Time: {now}\n"
            f"Caller: {caller_number}\n"
            f"Turns: {turn_count}\n"
            f"Call ID: {call_sid}\n"
            f"---\n"
            f"{summary}"
        )

        try:
            result = self.spruce.send_message_to_conversation(
                text=message,
                conversation_id=self.conversation_id,
                internal=True,
            )
            logger.info("Call summary posted to Spruce for %s", call_sid)
            return result
        except Exception:
            logger.exception(
                "Failed to post call summary to Spruce for %s", call_sid
            )
            return None
