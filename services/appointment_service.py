"""Service for fetching and organizing practice-wide appointment data."""

import logging
from collections import defaultdict
from datetime import datetime

from clients.elation_client import ElationClient

logger = logging.getLogger(__name__)


class AppointmentService:
    """Orchestrates fetching today's appointments and organizing them for analytics."""

    def __init__(self, elation_client: ElationClient = None):
        self.elation = elation_client or ElationClient()

    def fetch_todays_appointments(self) -> list[dict]:
        """Fetch all appointments for today across the entire practice."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        appointments = self.elation.get_appointments_for_date(today)
        enriched = self.elation.enrich_appointments(appointments)
        return enriched

    def organize_by_provider(self, appointments: list[dict]) -> dict[str, list[dict]]:
        """Group appointments by physician name."""
        by_provider = defaultdict(list)
        for appt in appointments:
            physician = appt.get("physician_detail", {})
            name = _format_physician_name(physician)
            by_provider[name].append(appt)
        return dict(by_provider)

    def organize_by_status(self, appointments: list[dict]) -> dict[str, int]:
        """Count appointments by status."""
        status_counts = defaultdict(int)
        for appt in appointments:
            status_obj = appt.get("status", {})
            status_name = status_obj.get("status", "Unknown") if isinstance(status_obj, dict) else str(status_obj)
            status_counts[status_name] += 1
        return dict(status_counts)

    def organize_by_time_block(self, appointments: list[dict]) -> dict[str, list[dict]]:
        """Group appointments into time blocks (morning, midday, afternoon)."""
        blocks = {
            "Early Morning (7-9 AM)": [],
            "Morning (9-12 PM)": [],
            "Midday (12-2 PM)": [],
            "Afternoon (2-5 PM)": [],
            "Evening (5+ PM)": [],
        }
        for appt in appointments:
            scheduled = appt.get("scheduled_date", "")
            try:
                dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                hour = dt.hour
            except (ValueError, AttributeError):
                blocks["Morning (9-12 PM)"].append(appt)
                continue

            if hour < 9:
                blocks["Early Morning (7-9 AM)"].append(appt)
            elif hour < 12:
                blocks["Morning (9-12 PM)"].append(appt)
            elif hour < 14:
                blocks["Midday (12-2 PM)"].append(appt)
            elif hour < 17:
                blocks["Afternoon (2-5 PM)"].append(appt)
            else:
                blocks["Evening (5+ PM)"].append(appt)

        return {k: v for k, v in blocks.items() if v}

    def compute_summary_stats(self, appointments: list[dict]) -> dict:
        """Compute high-level statistics for the clinical analytics summary."""
        unique_patients = set()
        unique_providers = set()
        total_duration_minutes = 0

        for appt in appointments:
            if appt.get("patient"):
                unique_patients.add(appt["patient"])
            if appt.get("physician"):
                unique_providers.add(appt["physician"])
            total_duration_minutes += appt.get("duration", 0) or 0

        return {
            "total_appointments": len(appointments),
            "unique_patients": len(unique_patients),
            "unique_providers": len(unique_providers),
            "total_duration_minutes": total_duration_minutes,
            "total_duration_hours": round(total_duration_minutes / 60, 1),
            "avg_duration_minutes": (
                round(total_duration_minutes / len(appointments), 1)
                if appointments
                else 0
            ),
            "status_breakdown": self.organize_by_status(appointments),
        }


def _format_physician_name(physician: dict) -> str:
    """Format physician name from the API response."""
    first = physician.get("first_name", "")
    last = physician.get("last_name", "")
    credentials = physician.get("credentials", "")
    if first and last:
        name = f"Dr. {first} {last}"
        if credentials:
            name += f", {credentials}"
        return name
    return "Unassigned Provider"
