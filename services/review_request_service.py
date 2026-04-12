"""Service for sending Google review requests to patients after checkout."""

import json
import logging
import os
from datetime import datetime

from clients.elation_client import ElationClient
from clients.spruce_client import SpruceClient
from config import ReviewRequestConfig

logger = logging.getLogger(__name__)


class ReviewRequestService:
    """Monitors checked-out appointments and sends review request SMS via Spruce.

    When a patient's appointment status goes to 'Checked Out' in Elation,
    this service sends them a thank-you message with a link to leave a
    Google review for the practice.

    Tracks processed appointments in a JSON file to avoid duplicate messages.
    """

    def __init__(
        self,
        elation_client: ElationClient = None,
        spruce_client: SpruceClient = None,
    ):
        self.elation = elation_client or ElationClient()
        self.spruce = spruce_client or SpruceClient()
        self.config = ReviewRequestConfig
        self._processed = self._load_processed()

    def _load_processed(self) -> dict:
        """Load the set of already-processed appointment IDs from disk.

        Returns a dict mapping appointment ID -> ISO timestamp of when
        the review request was sent.
        """
        path = self.config.PROCESSED_FILE
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read processed file %s, starting fresh", path)
        return {}

    def _save_processed(self):
        """Persist the processed appointment tracking data to disk."""
        path = self.config.PROCESSED_FILE
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._processed, f, indent=2)

    def _build_review_message(self, patient_first_name: str) -> str:
        """Build the personalized thank-you and review request message.

        Args:
            patient_first_name: The patient's first name for personalization.

        Returns:
            The formatted SMS message string.
        """
        return (
            f"Hi {patient_first_name}, thank you for visiting "
            f"{self.config.PRACTICE_NAME} today! "
            f"We truly value your trust in us. If you had a great experience, "
            f"we'd love for you to share it with others. "
            f"Please leave us a Google review here: {self.config.GOOGLE_REVIEW_URL} "
            f"— it means the world to our team. Thank you!"
        )

    @staticmethod
    def _extract_patient_phone(patient_detail: dict) -> str | None:
        """Extract the best phone number from a patient record.

        Prefers mobile numbers, falls back to any available phone.
        """
        phones = patient_detail.get("phones", [])
        if not phones:
            return None

        # Prefer mobile
        for phone in phones:
            if isinstance(phone, dict):
                phone_type = phone.get("phone_type", "").lower()
                if phone_type in ("mobile", "cell"):
                    return phone.get("phone", "")

        # Fall back to first available phone
        first = phones[0]
        if isinstance(first, dict):
            return first.get("phone", "")
        return str(first) if first else None

    def process_checked_out_appointments(self) -> int:
        """Poll Elation for checked-out appointments and send review requests.

        Fetches today's appointments, filters for checked-out status,
        and sends a review request SMS to each patient who hasn't already
        received one.

        Returns:
            The number of review requests sent in this polling cycle.
        """
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_count = 0

        try:
            checked_out = self.elation.get_checked_out_appointments(today)
        except Exception:
            logger.exception("Failed to fetch checked-out appointments from Elation")
            return 0

        if not checked_out:
            logger.debug("No checked-out appointments found")
            return 0

        for appt in checked_out:
            appt_id = str(appt.get("id", ""))
            if not appt_id:
                continue

            # Skip if already processed
            if appt_id in self._processed:
                continue

            patient_detail = appt.get("patient_detail", {})
            first_name = patient_detail.get("first_name", "").strip()
            if not first_name:
                first_name = "there"

            phone = self._extract_patient_phone(patient_detail)
            if not phone:
                logger.warning(
                    "No phone number for patient in appointment %s, skipping",
                    appt_id,
                )
                self._processed[appt_id] = {
                    "sent_at": datetime.utcnow().isoformat(),
                    "status": "skipped_no_phone",
                }
                continue

            message = self._build_review_message(first_name)

            try:
                self.spruce.send_patient_sms(phone, message)
                self._processed[appt_id] = {
                    "sent_at": datetime.utcnow().isoformat(),
                    "status": "sent",
                    "patient_first_name": first_name,
                }
                sent_count += 1
                logger.info(
                    "Review request sent for appointment %s (patient: %s)",
                    appt_id,
                    first_name,
                )
            except Exception:
                logger.exception(
                    "Failed to send review request for appointment %s",
                    appt_id,
                )

        self._save_processed()
        self._cleanup_old_entries()

        if sent_count > 0:
            logger.info("Sent %d review request(s) this cycle", sent_count)

        return sent_count

    def _cleanup_old_entries(self):
        """Remove processed entries older than 7 days to prevent file growth."""
        cutoff = datetime.utcnow().timestamp() - (7 * 24 * 3600)
        to_remove = []
        for appt_id, data in self._processed.items():
            if isinstance(data, dict):
                sent_at = data.get("sent_at", "")
            else:
                sent_at = str(data)
            try:
                entry_time = datetime.fromisoformat(sent_at).timestamp()
                if entry_time < cutoff:
                    to_remove.append(appt_id)
            except (ValueError, TypeError):
                continue

        for appt_id in to_remove:
            del self._processed[appt_id]

        if to_remove:
            self._save_processed()
            logger.debug("Cleaned up %d old processed entries", len(to_remove))
