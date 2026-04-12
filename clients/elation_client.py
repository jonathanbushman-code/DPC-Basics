"""Elation Health API client for OAuth authentication, appointments, fax inbox, and document filing."""

import logging
import time
from datetime import datetime, timedelta

import requests

from config import ElationConfig

logger = logging.getLogger(__name__)


class ElationClient:
    """Client for interacting with the Elation Health REST API (v2.0).

    Handles OAuth 2.0 authentication (client credentials grant) and provides
    methods to fetch appointments, patients, and physicians.
    """

    def __init__(self):
        self.config = ElationConfig
        self._access_token = None
        self._token_expiry = None
        self.session = requests.Session()

    def _authenticate(self):
        """Obtain an OAuth 2.0 access token using client credentials."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.config.CLIENT_ID,
            "client_secret": self.config.CLIENT_SECRET,
        }
        response = requests.post(self.config.TOKEN_ENDPOINT, data=payload)
        response.raise_for_status()
        data = response.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 60  # refresh 60s early
        self.session.headers.update({"Authorization": f"Bearer {self._access_token}"})
        logger.info("Elation OAuth token acquired, expires in %ds", expires_in)

    def _ensure_authenticated(self):
        """Refresh the token if it has expired or is not yet set."""
        if self._access_token is None or time.time() >= self._token_expiry:
            self._authenticate()

    def _get_paginated(self, url, params=None):
        """Fetch all pages of a paginated Elation API endpoint.

        Elation returns up to 100 results per page with offset/limit pagination.
        Rate limit: <3 requests/second.
        """
        self._ensure_authenticated()
        params = params or {}
        params.setdefault("limit", 100)
        params.setdefault("offset", 0)

        all_results = []
        while True:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            all_results.extend(results)

            if data.get("next"):
                params["offset"] += params["limit"]
                time.sleep(0.4)  # respect <3 calls/sec rate limit
            else:
                break

        return all_results

    def get_appointments_for_date(self, target_date: datetime) -> list[dict]:
        """Fetch all appointments for the entire practice on a given date.

        Args:
            target_date: The date to fetch appointments for.

        Returns:
            List of appointment dictionaries from the Elation API.
        """
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        params = {
            "from_date": start_of_day.isoformat() + "Z",
            "to_date": end_of_day.isoformat() + "Z",
        }
        logger.info(
            "Fetching appointments from %s to %s",
            params["from_date"],
            params["to_date"],
        )
        appointments = self._get_paginated(self.config.APPOINTMENTS_ENDPOINT, params)
        logger.info("Fetched %d appointments", len(appointments))
        return appointments

    def get_patient(self, patient_id: int) -> dict:
        """Fetch a single patient by ID."""
        self._ensure_authenticated()
        url = f"{self.config.PATIENTS_ENDPOINT}{patient_id}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_physician(self, physician_id: int) -> dict:
        """Fetch a single physician by ID."""
        self._ensure_authenticated()
        url = f"{self.config.PHYSICIANS_ENDPOINT}{physician_id}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def enrich_appointments(self, appointments: list[dict]) -> list[dict]:
        """Enrich appointment records with patient and physician details.

        Caches lookups to avoid redundant API calls across appointments.
        """
        patient_cache: dict[int, dict] = {}
        physician_cache: dict[int, dict] = {}

        for appt in appointments:
            patient_id = appt.get("patient")
            physician_id = appt.get("physician")

            if patient_id and patient_id not in patient_cache:
                try:
                    patient_cache[patient_id] = self.get_patient(patient_id)
                    time.sleep(0.4)  # rate limit
                except requests.HTTPError:
                    logger.warning("Failed to fetch patient %s", patient_id)
                    patient_cache[patient_id] = {}

            if physician_id and physician_id not in physician_cache:
                try:
                    physician_cache[physician_id] = self.get_physician(physician_id)
                    time.sleep(0.4)
                except requests.HTTPError:
                    logger.warning("Failed to fetch physician %s", physician_id)
                    physician_cache[physician_id] = {}

            appt["patient_detail"] = patient_cache.get(patient_id, {})
            appt["physician_detail"] = physician_cache.get(physician_id, {})

        return appointments

    # ── Fax Inbox Methods ──────────────────────────────────────────────

    def get_received_faxes(self, filing_status: str = "new") -> list[dict]:
        """Fetch received faxes from the Elation fax inbox.

        Args:
            filing_status: Filter by filing status. Use "new" for unfiled faxes.

        Returns:
            List of received fax dictionaries.
        """
        params = {}
        if filing_status:
            params["filing_status"] = filing_status

        logger.info("Fetching received faxes (status=%s)", filing_status)
        faxes = self._get_paginated(self.config.RECEIVED_FAXES_ENDPOINT, params)
        logger.info("Fetched %d received faxes", len(faxes))
        return faxes

    def get_received_fax(self, fax_id: int) -> dict:
        """Fetch a single received fax by ID."""
        self._ensure_authenticated()
        url = f"{self.config.RECEIVED_FAXES_ENDPOINT}{fax_id}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def download_fax_document(self, document_url: str) -> bytes:
        """Download the PDF content of a received fax.

        Args:
            document_url: The URL to the fax document PDF.

        Returns:
            Raw PDF bytes.
        """
        self._ensure_authenticated()
        response = self.session.get(document_url)
        response.raise_for_status()
        return response.content

    def update_received_fax(self, fax_id: int, data: dict) -> dict:
        """Update a received fax record (e.g. mark as filed).

        Args:
            fax_id: The fax ID to update.
            data: Fields to update (e.g. filing_status, patient, document_type).

        Returns:
            Updated fax record.
        """
        self._ensure_authenticated()
        url = f"{self.config.RECEIVED_FAXES_ENDPOINT}{fax_id}/"
        response = self.session.patch(url, json=data)
        response.raise_for_status()
        time.sleep(0.4)
        return response.json()

    # ── Patient Search Methods ─────────────────────────────────────────

    def search_patients(
        self,
        first_name: str = None,
        last_name: str = None,
        dob: str = None,
        search: str = None,
    ) -> list[dict]:
        """Search for patients by name, date of birth, or general search term.

        Args:
            first_name: Patient first name filter.
            last_name: Patient last name filter.
            dob: Date of birth in YYYY-MM-DD format.
            search: General search term.

        Returns:
            List of matching patient dictionaries.
        """
        self._ensure_authenticated()
        params = {}
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name
        if dob:
            params["dob"] = dob
        if search:
            params["search"] = search

        logger.info("Searching patients with params: %s", params)
        results = self._get_paginated(self.config.PATIENTS_ENDPOINT, params)
        logger.info("Found %d matching patients", len(results))
        return results

    # ── Document Filing Methods ────────────────────────────────────────

    def create_document(
        self,
        patient_id: int,
        document_type: str,
        file_content: bytes,
        filename: str,
        physician_id: int = None,
        description: str = "",
        document_date: str = None,
        chart_date: str = None,
    ) -> dict:
        """Create a document in a patient's chart.

        Args:
            patient_id: The patient to file the document under.
            document_type: The category (e.g. "Lab Report", "Referral Letter").
            file_content: Raw file bytes (typically PDF).
            filename: Name of the file being uploaded.
            physician_id: Provider to assign for review/sign-off.
            description: Description of the document.
            document_date: Date of the document (YYYY-MM-DD).
            chart_date: Date to display on the chart (YYYY-MM-DD).

        Returns:
            Created document record from Elation.
        """
        self._ensure_authenticated()

        if not document_date:
            document_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not chart_date:
            chart_date = document_date

        data = {
            "patient": patient_id,
            "document_type": document_type,
            "document_date": document_date,
            "chart_date": chart_date,
            "description": description,
        }
        if physician_id:
            data["sign_off_physician"] = physician_id

        files = {
            "file": (filename, file_content, "application/pdf"),
        }

        response = self.session.post(
            self.config.DOCUMENTS_ENDPOINT,
            data=data,
            files=files,
        )
        response.raise_for_status()
        time.sleep(0.4)
        logger.info(
            "Document created for patient %d (type=%s, assigned to physician=%s)",
            patient_id,
            document_type,
            physician_id,
        )
        return response.json()
