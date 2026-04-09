"""Service for generating clinical analytics summary PDF from appointment data."""

import logging
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from config import SUMMARY_OUTPUT_DIR
from services.appointment_service import AppointmentService

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


class AnalyticsService:
    """Generates a clinical analytics summary document from appointment data."""

    def __init__(self, appointment_service: AppointmentService = None):
        self.appointment_service = appointment_service or AppointmentService()
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    def generate_summary(self, appointments: list[dict]) -> str:
        """Generate a clinical analytics summary PDF for the given appointments.

        Args:
            appointments: Enriched appointment records from the Elation API.

        Returns:
            File path to the generated PDF.
        """
        stats = self.appointment_service.compute_summary_stats(appointments)
        providers = self.appointment_service.organize_by_provider(appointments)
        time_blocks = self.appointment_service.organize_by_time_block(appointments)

        # Transform appointments for template rendering
        providers_rendered = {
            name: [_render_appointment(a) for a in appts]
            for name, appts in providers.items()
        }
        time_blocks_rendered = {
            block: [_render_appointment(a) for a in appts]
            for block, appts in time_blocks.items()
        }

        template = self.jinja_env.get_template("clinical_summary.html")
        now = datetime.utcnow()
        html_content = template.render(
            report_date=now.strftime("%A, %B %d, %Y"),
            stats=stats,
            providers=providers_rendered,
            time_blocks=time_blocks_rendered,
            generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        )

        os.makedirs(SUMMARY_OUTPUT_DIR, exist_ok=True)
        date_str = now.strftime("%Y-%m-%d")

        # Try PDF generation with weasyprint; fall back to HTML if unavailable
        pdf_path = os.path.join(SUMMARY_OUTPUT_DIR, f"clinical_summary_{date_str}.pdf")
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(pdf_path)
            logger.info("PDF summary generated: %s", pdf_path)
            return pdf_path
        except ImportError:
            logger.warning(
                "weasyprint not available, falling back to HTML output"
            )
            html_path = os.path.join(
                SUMMARY_OUTPUT_DIR, f"clinical_summary_{date_str}.html"
            )
            with open(html_path, "w") as f:
                f.write(html_content)
            logger.info("HTML summary generated: %s", html_path)
            return html_path


def _render_appointment(appt: dict) -> dict:
    """Transform a raw appointment dict into template-friendly format."""
    scheduled = appt.get("scheduled_date", "")
    try:
        dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
        scheduled_time = dt.strftime("%I:%M %p")
    except (ValueError, AttributeError):
        scheduled_time = "N/A"

    patient = appt.get("patient_detail", {})
    patient_name = _format_patient_name(patient)

    physician = appt.get("physician_detail", {})
    provider_name = _format_physician_name(physician)

    status_obj = appt.get("status", {})
    if isinstance(status_obj, dict):
        status_text = status_obj.get("status", "Unknown")
    else:
        status_text = str(status_obj)

    return {
        "scheduled_time": scheduled_time,
        "patient_name": patient_name,
        "provider_name": provider_name,
        "reason": appt.get("reason", ""),
        "description": appt.get("description", ""),
        "duration": appt.get("duration"),
        "status_text": status_text,
        "status_class": status_text.lower().replace(" ", "-"),
    }


def _format_patient_name(patient: dict) -> str:
    first = patient.get("first_name", "")
    last = patient.get("last_name", "")
    if first and last:
        return f"{last}, {first}"
    return "Unknown Patient"


def _format_physician_name(physician: dict) -> str:
    first = physician.get("first_name", "")
    last = physician.get("last_name", "")
    if first and last:
        return f"Dr. {first} {last}"
    return "Unassigned"
