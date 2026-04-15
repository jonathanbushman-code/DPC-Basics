"""Message handler for the Reliant DPC Spruce chatbot.

Orchestrates the flow: receive message -> triage -> respond or escalate.
"""

import logging

from chatbot import triage_engine, knowledge_base
from chatbot.triage_engine import TriageLevel
from clients.spruce_client import SpruceClient
from config import ChatbotConfig

logger = logging.getLogger(__name__)


class MessageHandler:
    """Processes incoming patient messages and sends appropriate responses.

    Flow for each incoming message:
    1. Run through the triage engine to assess medical urgency.
    2. If EMERGENCY: send crisis response and escalate to provider.
    3. If URGENT/MODERATE: send acknowledgment and escalate to provider.
    4. If LOW: search the knowledge base for a relevant answer.
       - If found: send the KB answer.
       - If not found: send the default response and optionally escalate.
    """

    def __init__(self, spruce_client: SpruceClient = None):
        self.spruce = spruce_client or SpruceClient()

    def handle(self, conversation_id: str, message_text: str, sender_name: str = "Patient") -> dict:
        """Process an incoming message and respond appropriately.

        Args:
            conversation_id: The Spruce conversation to reply in.
            message_text: The text content of the incoming message.
            sender_name: Display name of the sender (for logging).

        Returns:
            A dict summarizing what action was taken.
        """
        logger.info(
            "Processing message from %s in conversation %s",
            sender_name,
            conversation_id,
        )

        # Step 1: Triage for medical urgency
        triage_result = triage_engine.assess(message_text)
        logger.info(
            "Triage result: level=%s category=%s escalate=%s",
            triage_result.level.name,
            triage_result.matched_category,
            triage_result.should_escalate,
        )

        # Step 2: Handle based on triage level
        if triage_result.level == TriageLevel.EMERGENCY:
            return self._handle_emergency(conversation_id, triage_result, sender_name)

        if triage_result.level in (TriageLevel.URGENT, TriageLevel.MODERATE):
            return self._handle_medical(conversation_id, triage_result, sender_name)

        # Step 3: LOW triage — try the knowledge base
        return self._handle_general(conversation_id, message_text, sender_name)

    def _handle_emergency(self, conversation_id: str, triage_result, sender_name: str) -> dict:
        """Handle emergency-level messages: auto-respond and escalate."""
        # Send the emergency auto-response to the patient
        self._send_reply(conversation_id, triage_result.auto_response)

        # Escalate to the care team
        self._escalate_to_team(
            conversation_id=conversation_id,
            level="EMERGENCY",
            category=triage_result.matched_category,
            sender_name=sender_name,
        )

        return {
            "action": "emergency_response",
            "level": "EMERGENCY",
            "category": triage_result.matched_category,
            "escalated": True,
        }

    def _handle_medical(self, conversation_id: str, triage_result, sender_name: str) -> dict:
        """Handle urgent/moderate medical messages: acknowledge and escalate."""
        self._send_reply(conversation_id, triage_result.auto_response)

        self._escalate_to_team(
            conversation_id=conversation_id,
            level=triage_result.level.name,
            category=triage_result.matched_category,
            sender_name=sender_name,
        )

        return {
            "action": "medical_escalation",
            "level": triage_result.level.name,
            "category": triage_result.matched_category,
            "escalated": True,
        }

    def _handle_general(self, conversation_id: str, message_text: str, sender_name: str) -> dict:
        """Handle non-medical messages using the knowledge base."""
        kb_response = knowledge_base.find_response(message_text)

        if kb_response:
            self._send_reply(conversation_id, kb_response)
            return {
                "action": "kb_response",
                "level": "LOW",
                "escalated": False,
            }

        # No KB match — send the default response
        default = knowledge_base.get_default_response()
        self._send_reply(conversation_id, default)

        return {
            "action": "default_response",
            "level": "LOW",
            "escalated": False,
        }

    def _send_reply(self, conversation_id: str, text: str):
        """Send a chatbot reply to the patient's conversation."""
        try:
            self.spruce.send_message_to_conversation(
                text=text,
                conversation_id=conversation_id,
                internal=False,
            )
            logger.info("Reply sent to conversation %s", conversation_id)
        except Exception:
            logger.exception("Failed to send reply to conversation %s", conversation_id)

    def _escalate_to_team(
        self,
        conversation_id: str,
        level: str,
        category: str,
        sender_name: str,
    ):
        """Send an internal note to the care team about an escalation.

        Posts an internal-only message to the same conversation so the
        clinical team sees the alert when they open the thread.
        Optionally also posts to a dedicated escalation conversation.
        """
        internal_note = (
            f"[CHATBOT ESCALATION - {level}]\n\n"
            f"A message from {sender_name} has been flagged for provider review.\n"
            f"Category: {category}\n"
            f"Triage Level: {level}\n\n"
            f"Please review the conversation and respond to the patient."
        )

        try:
            # Post an internal note in the patient's conversation
            self.spruce.send_message_to_conversation(
                text=internal_note,
                conversation_id=conversation_id,
                internal=True,
            )
            logger.info(
                "Escalation note posted (internal) to conversation %s [%s / %s]",
                conversation_id,
                level,
                category,
            )
        except Exception:
            logger.exception("Failed to post escalation note to conversation %s", conversation_id)

        # If a dedicated escalation conversation is configured, also notify there
        escalation_id = ChatbotConfig.ESCALATION_CONVERSATION_ID
        if escalation_id and escalation_id != conversation_id:
            summary = (
                f"[CHATBOT ESCALATION - {level}]\n\n"
                f"Patient: {sender_name}\n"
                f"Category: {category}\n"
                f"Conversation requires provider attention."
            )
            try:
                self.spruce.send_message_to_conversation(
                    text=summary,
                    conversation_id=escalation_id,
                    internal=True,
                )
                logger.info("Escalation summary sent to escalation conversation %s", escalation_id)
            except Exception:
                logger.exception("Failed to send to escalation conversation %s", escalation_id)
