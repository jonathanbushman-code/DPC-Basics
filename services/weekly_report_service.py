"""Top-level service for the SPRUS weekly call/SMS dashboard.

Pulls one week of Spruce activity, rolls it up per-phone and per-provider,
renders a self-contained HTML/PDF (with an embedded hourly-volume chart),
and delivers it to a Spruce conversation as an internal message.
"""

import json
import logging
import os
from datetime import datetime, timedelta

import pytz
from jinja2 import Environment, FileSystemLoader

from clients.elation_client import ElationClient
from clients.spruce_client import SpruceClient
from clients.spruce_reporting_client import SpruceReportingClient
from config import (
    SUMMARY_OUTPUT_DIR,
    ScheduleConfig,
    SpruceConfig,
    WeeklyReportConfig,
)
from services.chart_service import png_to_data_uri, render_hourly_volume_chart_png
from services.weekly_aggregation import WeeklyAggregator

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


class WeeklyReportService:
    def __init__(
        self,
        reporting_client: SpruceReportingClient = None,
        spruce_client: SpruceClient = None,
        elation_client: ElationClient = None,
    ):
        self.reporting = reporting_client or SpruceReportingClient()
        self.spruce = spruce_client or SpruceClient()
        self.elation = elation_client if elation_client is not None else (
            ElationClient() if WeeklyReportConfig.ENRICH_PROVIDERS else None
        )
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    # ---------- public entry points ----------

    def run(self, send: bool = True) -> str:
        """Generate the weekly report and (optionally) deliver it. Returns file path."""
        tz = pytz.timezone(ScheduleConfig.TIMEZONE)
        now_local = datetime.now(tz)
        week_end = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = week_end - timedelta(days=7)

        logger.info("Generating weekly report for %s -> %s", week_start, week_end)
        calls = self.reporting.get_calls(week_start, week_end)
        messages = self.reporting.get_messages(week_start, week_end)

        phone_mapping = self._load_phone_mapping()
        provider_lookup = self._build_provider_lookup() if self.elation else None

        aggregator = WeeklyAggregator(
            timezone=ScheduleConfig.TIMEZONE,
            provider_lookup=provider_lookup,
            phone_mapping=phone_mapping,
        )
        report = aggregator.aggregate(calls, messages, week_start, week_end)

        chart_png = render_hourly_volume_chart_png(report["hourly"])
        chart_data_uri = png_to_data_uri(chart_png)

        report_path = self._render(report, chart_data_uri)
        logger.info("Weekly report rendered: %s", report_path)

        if send:
            self._deliver(report_path)

        return report_path

    # ---------- helpers ----------

    def _load_phone_mapping(self) -> dict:
        path = WeeklyReportConfig.PHONE_MAPPING_FILE
        if not path or not os.path.exists(path):
            logger.info("No phone mapping file at %s; using raw phone IDs", path)
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read phone mapping %s: %s", path, exc)
            return {}

    def _build_provider_lookup(self):
        """Return a callable patient_id -> provider name, with caching.

        Looks up the patient in Elation to get their assigned physician.
        Returns 'Unassigned / Unknown' on any failure so reporting still
        succeeds when an external system is down.
        """
        cache: dict[str, str] = {}

        def lookup(patient_id: str) -> str:
            if patient_id in cache:
                return cache[patient_id]
            try:
                patient = self.elation.get_patient(int(patient_id))
            except Exception as exc:
                logger.debug("Patient %s not found in Elation: %s", patient_id, exc)
                cache[patient_id] = "Unassigned / Unknown"
                return cache[patient_id]
            physician_id = patient.get("primary_physician") or patient.get("physician")
            if not physician_id:
                cache[patient_id] = "Unassigned / Unknown"
                return cache[patient_id]
            try:
                physician = self.elation.get_physician(int(physician_id))
                first = physician.get("first_name", "")
                last = physician.get("last_name", "")
                name = f"Dr. {first} {last}".strip() if (first or last) else "Unassigned / Unknown"
            except Exception:
                name = "Unassigned / Unknown"
            cache[patient_id] = name
            return name

        return lookup

    def _render(self, report: dict, chart_data_uri: str) -> str:
        template = self.jinja_env.get_template("weekly_report.html")
        html_content = template.render(
            week_start=report["week_start"].strftime("%A, %B %d, %Y"),
            week_end=report["week_end"].strftime("%A, %B %d, %Y"),
            totals=report["totals"],
            per_phone=report["per_phone"],
            by_provider=report["by_provider"],
            hourly=report["hourly"],
            chart_data_uri=chart_data_uri,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

        os.makedirs(SUMMARY_OUTPUT_DIR, exist_ok=True)
        date_str = report["week_end"].strftime("%Y-%m-%d")
        pdf_path = os.path.join(SUMMARY_OUTPUT_DIR, f"weekly_sprus_{date_str}.pdf")
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(pdf_path)
            return pdf_path
        except ImportError:
            logger.warning("weasyprint not available, falling back to HTML output")
            html_path = os.path.join(SUMMARY_OUTPUT_DIR, f"weekly_sprus_{date_str}.html")
            with open(html_path, "w") as f:
                f.write(html_content)
            return html_path

    def _deliver(self, file_path: str) -> None:
        conversation_id = WeeklyReportConfig.CONVERSATION_ID or SpruceConfig.CONVERSATION_ID
        if not conversation_id:
            logger.warning("No conversation ID configured; skipping delivery")
            return

        message_text = (
            "Weekly SPRUS Call & Messaging Report. "
            "Per-phone breakdown of missed calls (during business hours), "
            "talk time, and SMS volume, plus an hourly call-volume chart."
        )

        if file_path.endswith(".pdf"):
            self.spruce.send_summary_document(
                file_path=file_path,
                message_text=message_text,
                conversation_id=conversation_id,
            )
        else:
            content_type = "text/html"
            media_id = self.spruce.upload_media(file_path, content_type=content_type)
            self.spruce.send_message_to_conversation(
                text=message_text,
                conversation_id=conversation_id,
                attachment_ids=[media_id],
            )
        logger.info("Weekly report delivered to conversation %s", conversation_id)
