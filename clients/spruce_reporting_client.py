"""Spruce Health API client extension for reporting (calls + messages).

Pulls call history and SMS records over a date range so the weekly report
can aggregate them by phone ID, by provider, and by hour-of-day.

The endpoint paths and field names are configurable via env vars because
Spruce's reporting endpoints can vary by account; the client tolerates a
few common shapes (`results` vs `data`, `direction` vs `inbound` flag).
"""

import logging
import time
from datetime import datetime
from typing import Iterable

import requests

from config import SpruceConfig

logger = logging.getLogger(__name__)


class SpruceReportingClient:
    """Read-only Spruce client for fetching telephony and messaging activity."""

    def __init__(self):
        self.config = SpruceConfig
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.config.API_TOKEN}",
            "Accept": "application/json",
        })

    def _paginate(self, url: str, params: dict) -> Iterable[dict]:
        """Yield records across pagination. Tolerates `results`/`data`
        envelopes and either offset or `next` cursor pagination.
        """
        params = dict(params)
        params.setdefault("limit", 100)
        offset = 0
        while True:
            params["offset"] = offset
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                page = data
                has_more = False
            else:
                page = data.get("results") or data.get("data") or []
                has_more = bool(data.get("next") or data.get("has_more"))

            for record in page:
                yield record

            if not has_more or not page:
                break
            offset += params["limit"]
            time.sleep(0.25)  # be polite to the API

    def get_calls(self, start: datetime, end: datetime) -> list[dict]:
        """Fetch all call records (incoming, outgoing, missed) in a window.

        Returned dicts are passed through unchanged; aggregation logic
        normalizes the relevant fields.
        """
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
        logger.info("Fetching Spruce calls %s -> %s", params["from"], params["to"])
        calls = list(self._paginate(self.config.CALLS_ENDPOINT, params))
        logger.info("Fetched %d calls", len(calls))
        return calls

    def get_messages(self, start: datetime, end: datetime) -> list[dict]:
        """Fetch all messages (SMS + secure) in a window."""
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
        logger.info("Fetching Spruce messages %s -> %s", params["from"], params["to"])
        messages = list(self._paginate(self.config.MESSAGES_ENDPOINT, params))
        logger.info("Fetched %d messages", len(messages))
        return messages

    def get_phone_numbers(self) -> list[dict]:
        """Fetch organization phone numbers (used to resolve phone IDs)."""
        try:
            return list(self._paginate(self.config.PHONE_NUMBERS_ENDPOINT, {}))
        except requests.HTTPError as exc:
            logger.warning("phone_numbers endpoint not available: %s", exc)
            return []
