"""Entry point for the Reliant DPC chatbot webhook server.

Usage:
    python chatbot_server.py                  Start the webhook server
    python chatbot_server.py --register-webhook  Register the webhook with Spruce
    python chatbot_server.py --list-webhooks     List registered webhook endpoints
"""

import argparse
import logging
import sys

from config import ChatbotConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("chatbot.log"),
    ],
)
logger = logging.getLogger(__name__)


def start_server():
    """Start the Flask webhook server."""
    from chatbot.webhook_server import run_server

    if not ChatbotConfig.ENABLED:
        logger.error("Chatbot is disabled (CHATBOT_ENABLED=false). Exiting.")
        sys.exit(1)

    run_server()


def register_webhook():
    """Register this server's webhook URL with Spruce."""
    from clients.spruce_client import SpruceClient

    public_url = ChatbotConfig.PUBLIC_URL
    if not public_url:
        logger.error(
            "CHATBOT_PUBLIC_URL is not set. Set it to the publicly-accessible "
            "URL of this server (e.g. https://yourdomain.com/webhook/spruce)."
        )
        sys.exit(1)

    webhook_url = f"{public_url.rstrip('/')}{ChatbotConfig.WEBHOOK_PATH}"
    logger.info("Registering webhook: %s", webhook_url)

    client = SpruceClient()
    result = client.register_webhook(url=webhook_url)

    logger.info("Webhook registered successfully!")
    logger.info("Endpoint ID: %s", result.get("id", "N/A"))

    secret = result.get("secret") or result.get("signingSecret")
    if secret:
        logger.info(
            "IMPORTANT: Save this webhook secret in your .env file as "
            "SPRUCE_WEBHOOK_SECRET=%s",
            secret,
        )


def list_webhooks():
    """List all registered webhook endpoints."""
    from clients.spruce_client import SpruceClient

    client = SpruceClient()
    endpoints = client.list_webhooks()

    if not endpoints:
        logger.info("No webhook endpoints registered.")
        return

    for ep in endpoints:
        if isinstance(ep, dict):
            logger.info(
                "  ID: %s | URL: %s | Name: %s",
                ep.get("id", "?"),
                ep.get("url", "?"),
                ep.get("name", "?"),
            )
        else:
            logger.info("  %s", ep)


def main():
    parser = argparse.ArgumentParser(
        description="Reliant DPC Chatbot - Spruce Webhook Server"
    )
    parser.add_argument(
        "--register-webhook",
        action="store_true",
        help="Register the webhook endpoint with Spruce",
    )
    parser.add_argument(
        "--list-webhooks",
        action="store_true",
        help="List all registered webhook endpoints",
    )
    args = parser.parse_args()

    if args.register_webhook:
        register_webhook()
    elif args.list_webhooks:
        list_webhooks()
    else:
        start_server()


if __name__ == "__main__":
    main()
