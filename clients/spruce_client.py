"""Spruce Health API client for uploading media, sending messages, and fetching logs."""

import logging
import os
import time

import requests

from config import SpruceConfig

logger = logging.getLogger(__name__)

# Delay between paginated API requests to respect rate limits
_RATE_LIMIT_DELAY = 0.4


class SpruceClient:
    """Client for interacting with the Spruce Health REST API.

    Handles Bearer token authentication and provides methods to upload
    documents, send messages, and retrieve call/message logs.
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

    # ------------------------------------------------------------------
    # Data retrieval methods for weekly reports
    # ------------------------------------------------------------------

    def _paginate(self, url: str, params: dict) -> list[dict]:
        """Fetch all pages from a paginated Spruce endpoint.

        Spruce uses token-based pagination: responses include ``hasMore``
        and ``paginationToken``.  Pass the token back as a query parameter
        to retrieve subsequent pages.
        """
        all_records: list[dict] = []
        while True:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            body = response.json()

            # Records may live under "data", "results", or at the top level
            records = body.get("data") or body.get("results") or []
            all_records.extend(records)

            has_more = body.get("hasMore", False)
            token = body.get("paginationToken")
            if not has_more or not token:
                break
            params["paginationToken"] = token
            time.sleep(_RATE_LIMIT_DELAY)

        return all_records

    def get_conversations(self, start_from: str = None) -> list[dict]:
        """List conversations, optionally filtered from a start time.

        Spruce models all communications (calls, SMS, fax, secure messages)
        as conversations.  Each conversation has items (individual call
        records, text messages, etc.).

        Args:
            start_from: ISO-8601 datetime to fetch conversations from.

        Returns:
            List of conversation dicts.
        """
        params = {"order": "created"}
        if start_from:
            params["startFrom"] = start_from
        records = self._paginate(self.config.CONVERSATIONS_ENDPOINT, params)
        logger.info("Fetched %d conversations", len(records))
        return records

    def get_conversation_item(self, item_id: str) -> dict:
        """Fetch a single conversation item (call record, message, etc.).

        The response includes event data with call-specific fields like
        ``answered``, ``duration``, ``failed``, ``initiatedBy``, and
        ``recordings`` for call-type items.

        Args:
            item_id: The conversation-item ID.

        Returns:
            The conversation-item dict.
        """
        url = f"{self.config.CONVERSATION_ITEMS_ENDPOINT}/{item_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_internal_endpoints(self) -> list[dict]:
        """List all internal endpoints (phone numbers, fax, email, Spruce links).

        These represent the org's communication channels — the phone numbers
        correspond to the physical phones at each desk.

        Returns:
            List of endpoint dicts with id, label/name, address/number, type.
        """
        records = self._paginate(self.config.INTERNAL_ENDPOINTS_ENDPOINT, {})
        logger.info("Fetched %d internal endpoints", len(records))
        return records
