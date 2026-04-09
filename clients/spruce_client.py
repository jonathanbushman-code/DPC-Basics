"""Spruce Health API client for uploading media and sending messages."""

import logging
import os

import requests

from config import SpruceConfig

logger = logging.getLogger(__name__)


class SpruceClient:
    """Client for interacting with the Spruce Health REST API.

    Handles Bearer token authentication and provides methods to upload
    documents and send messages to Spruce conversations.
    """

    def __init__(self):
        self.config = SpruceConfig
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.config.API_TOKEN}",
        })

    def upload_media(self, file_path: str, content_type: str = "application/pdf") -> str:
        """Upload a file to Spruce and return the media ID.

        Uses multipart form upload. The returned media ID can be referenced
        in message attachments and reused across multiple messages.

        Args:
            file_path: Local path to the file to upload.
            content_type: MIME type of the file.

        Returns:
            The media ID string for use in message attachments.
        """
        filename = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            files = {
                "media": (filename, f, content_type),
            }
            response = self.session.post(
                self.config.UPLOAD_MEDIA_ENDPOINT,
                files=files,
            )
        response.raise_for_status()
        data = response.json()
        media_id = data.get("mediaId") or data.get("id")
        logger.info("Uploaded media '%s' -> media_id=%s", filename, media_id)
        return media_id

    def send_message_to_conversation(
        self,
        text: str,
        conversation_id: str = None,
        attachment_ids: list[str] = None,
        internal: bool = True,
    ) -> dict:
        """Post a message (with optional attachments) to a Spruce conversation.

        Uses the Spruce structured body format with typed elements.
        For team/note conversations, set internal=True so the message is
        visible only to internal team members.

        Args:
            text: The message body text.
            conversation_id: Target conversation ID (defaults to config).
            attachment_ids: List of media IDs from upload_media().
            internal: Whether this is an internal-only message.

        Returns:
            The API response as a dictionary.
        """
        conv_id = conversation_id or self.config.CONVERSATION_ID
        url = f"{self.config.BASE_URL}/v1/conversations/{conv_id}/messages"

        # Spruce uses a structured body array with typed elements
        body_elements = [{"type": "text", "value": text}]
        if attachment_ids:
            for mid in attachment_ids:
                body_elements.append({"type": "attachment", "attachmentID": mid})

        payload = {
            "internal": internal,
            "body": body_elements,
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()
        logger.info("Message sent to conversation %s", conv_id)
        return response.json()

    def send_summary_document(
        self,
        file_path: str,
        message_text: str,
        conversation_id: str = None,
    ) -> dict:
        """Upload a document and send it as a message to a Spruce conversation.

        This is the primary method used by the scheduler to deliver the
        clinical analytics summary to the target Spruce user.

        Args:
            file_path: Path to the PDF summary file.
            message_text: Accompanying message text.
            conversation_id: Target conversation (defaults to config).

        Returns:
            The API response from the message post.
        """
        media_id = self.upload_media(file_path)
        return self.send_message_to_conversation(
            text=message_text,
            conversation_id=conversation_id,
            attachment_ids=[media_id],
            internal=True,
        )
