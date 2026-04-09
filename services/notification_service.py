"""Service for sending clinical analytics summaries via Spruce Health."""

import logging

from clients.spruce_client import SpruceClient

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles delivery of clinical analytics summaries through Spruce."""

    def __init__(self, spruce_client: SpruceClient = None):
        self.spruce = spruce_client or SpruceClient()

    def send_daily_summary(self, file_path: str) -> dict:
        """Send the daily clinical analytics summary PDF to the configured Spruce conversation.

        Args:
            file_path: Path to the generated summary document (PDF or HTML).

        Returns:
            The Spruce API response.
        """
        message_text = (
            "Daily Clinical Analytics Summary is ready for review. "
            "Please see the attached document for today's practice-wide "
            "appointment overview, provider breakdown, and key metrics."
        )
        logger.info("Sending summary document: %s", file_path)

        content_type = "application/pdf" if file_path.endswith(".pdf") else "text/html"

        if file_path.endswith(".pdf"):
            result = self.spruce.send_summary_document(
                file_path=file_path,
                message_text=message_text,
            )
        else:
            # For HTML fallback, upload and send as attachment
            media_id = self.spruce.upload_media(file_path, content_type=content_type)
            result = self.spruce.send_message_to_conversation(
                text=message_text,
                attachment_ids=[media_id],
            )

        logger.info("Summary delivered successfully via Spruce")
        return result
