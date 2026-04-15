"""Flask webhook server for receiving Spruce Health events.

Listens for conversationItem.created webhook events from Spruce, extracts
the incoming message text, and routes it through the chatbot message handler.
"""

import hashlib
import hmac
import json
import logging

from flask import Flask, request, jsonify

from chatbot.message_handler import MessageHandler
from config import SpruceConfig, ChatbotConfig

logger = logging.getLogger(__name__)

app = Flask(__name__)


def _verify_signature(payload: bytes, signature: str) -> bool:
    """Verify the X-Spruce-Signature header using HMAC-SHA256.

    Spruce signs webhook payloads with the secret provided at endpoint
    registration time.  If no webhook secret is configured, signature
    verification is skipped (useful during local development).
    """
    secret = SpruceConfig.WEBHOOK_SECRET
    if not secret:
        logger.warning("SPRUCE_WEBHOOK_SECRET not set — skipping signature verification")
        return True

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def _is_bot_message(event: dict) -> bool:
    """Return True if the message was sent by the chatbot / API itself.

    Prevents infinite reply loops by checking whether the message
    originated from an internal API source.
    """
    author = event.get("author", {})
    # Spruce marks API-originated messages; check common indicators
    if author.get("type") == "api":
        return True
    if author.get("entityType") == "api":
        return True
    # If the message has a requestID it was sent via the API (our own reply)
    if event.get("requestID"):
        return True
    return False


def _extract_message_text(event: dict) -> str:
    """Extract plain-text content from a Spruce conversationItem event."""
    # The body may be a structured array of elements or a plain string
    body = event.get("body", [])
    if isinstance(body, str):
        return body.strip()

    parts = []
    if isinstance(body, list):
        for element in body:
            if isinstance(element, dict) and element.get("type") == "text":
                parts.append(element.get("value", ""))
            elif isinstance(element, str):
                parts.append(element)

    # Fallback: some events put text in a "text" field directly
    if not parts:
        text = event.get("text", "")
        if text:
            parts.append(text)

    return " ".join(parts).strip()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "reliant-dpc-chatbot"})


@app.route(ChatbotConfig.WEBHOOK_PATH, methods=["POST"])
def spruce_webhook():
    """Handle incoming Spruce webhook events.

    Expected event type: conversationItem.created
    The payload includes the message body, author info, and conversation ID.
    """
    # Verify webhook signature
    signature = request.headers.get("X-Spruce-Signature", "")
    if not _verify_signature(request.data, signature):
        logger.warning("Invalid webhook signature — rejecting request")
        return jsonify({"error": "invalid signature"}), 401

    try:
        payload = request.get_json(force=True)
    except Exception:
        logger.exception("Failed to parse webhook payload")
        return jsonify({"error": "invalid payload"}), 400

    event_type = payload.get("type", "")
    logger.info("Received webhook event: %s", event_type)

    # We only handle new conversation items (messages)
    if event_type != "conversationItem.created":
        logger.debug("Ignoring event type: %s", event_type)
        return jsonify({"status": "ignored", "reason": "unsupported event type"}), 200

    event = payload.get("data", payload)

    # Skip messages sent by the bot itself to avoid reply loops
    if _is_bot_message(event):
        logger.debug("Ignoring bot-originated message")
        return jsonify({"status": "ignored", "reason": "bot message"}), 200

    # Extract conversation ID and message text
    conversation = event.get("conversation", {})
    conversation_id = conversation.get("id", "")
    if not conversation_id:
        # Some payloads nest the conversation ID differently
        conversation_id = event.get("conversationID", "")

    message_text = _extract_message_text(event)
    sender_name = event.get("author", {}).get("displayName", "Patient")

    if not conversation_id or not message_text:
        logger.warning(
            "Missing conversation_id or message_text — conversation_id=%s text=%r",
            conversation_id,
            message_text[:100] if message_text else "",
        )
        return jsonify({"status": "ignored", "reason": "missing data"}), 200

    logger.info(
        "Processing message from '%s' in conversation %s: %s",
        sender_name,
        conversation_id,
        message_text[:100],
    )

    # Process through the chatbot handler
    handler = MessageHandler()
    result = handler.handle(
        conversation_id=conversation_id,
        message_text=message_text,
        sender_name=sender_name,
    )

    logger.info("Handler result: %s", result)
    return jsonify({"status": "processed", **result}), 200


def run_server():
    """Start the webhook server."""
    logger.info(
        "Starting chatbot webhook server on %s:%s",
        ChatbotConfig.WEBHOOK_HOST,
        ChatbotConfig.WEBHOOK_PORT,
    )
    app.run(
        host=ChatbotConfig.WEBHOOK_HOST,
        port=ChatbotConfig.WEBHOOK_PORT,
        debug=False,
    )
