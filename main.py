"""Daily Clinical Analytics Summary Agent & Automated Fax Filing Agent.

This agent runs on a schedule to:
1. Fetch today's appointments from Elation Health at 12:01 AM
2. Generate a clinical analytics summary PDF
3. Send the summary to a specific Spruce Health user at 7:00 AM
4. Pull and file incoming faxes to patient charts hourly:
   - Monday-Thursday: 7 AM to 4 PM (on the hour)
   - Friday: 7 AM to 11 AM (on the hour)
"""

import logging
import os
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config import ScheduleConfig, SUMMARY_OUTPUT_DIR
from services.appointment_service import AppointmentService
from services.analytics_service import AnalyticsService
from services.notification_service import NotificationService
from services.fax_filing_service import FaxFilingService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log"),
    ],
)
logger = logging.getLogger(__name__)

# Module-level state for the summary file path between the two scheduled jobs
_daily_summary_path: str | None = None


def fetch_and_generate():
    """12:01 AM job: Fetch today's appointments and generate the summary."""
    global _daily_summary_path
    logger.info("=== Starting daily appointment fetch ===")

    try:
        appt_service = AppointmentService()
        analytics_service = AnalyticsService(appt_service)

        appointments = appt_service.fetch_todays_appointments()
        logger.info("Fetched %d appointments for today", len(appointments))

        if not appointments:
            logger.warning("No appointments found for today. Generating empty summary.")

        summary_path = analytics_service.generate_summary(appointments)
        _daily_summary_path = summary_path
        logger.info("Summary generated: %s", summary_path)

    except Exception:
        logger.exception("Failed to fetch appointments or generate summary")
        _daily_summary_path = None


def send_summary():
    """7:00 AM job: Send the pre-generated summary via Spruce."""
    global _daily_summary_path
    logger.info("=== Starting summary delivery ===")

    if _daily_summary_path is None or not os.path.exists(_daily_summary_path):
        logger.error(
            "No summary file available to send. Path: %s", _daily_summary_path
        )
        return

    try:
        notification_service = NotificationService()
        notification_service.send_daily_summary(_daily_summary_path)
        logger.info("Summary delivered successfully")
    except Exception:
        logger.exception("Failed to send summary via Spruce")


def process_fax_inbox():
    """Hourly job: Pull unfiled faxes and file them to patient charts.

    Runs Mon-Thu 7am-4pm and Fri 7am-11am. Each fax is:
    1. Analyzed to identify the patient (name, DOB from OCR text/metadata)
    2. Matched to a patient record in Elation
    3. Classified by document type (Lab Report, Imaging, Referral, etc.)
    4. Filed to the patient's chart with the fax PDF attached
    5. Assigned to the patient's provider for review and sign-off
    6. Marked as filed in the fax inbox
    """
    logger.info("=== Starting fax inbox processing ===")

    try:
        fax_service = FaxFilingService()
        result = fax_service.process_fax_inbox()

        logger.info(
            "Fax filing complete: %d total, %d filed, %d skipped, %d failed",
            result["total"],
            result["filed"],
            result["skipped"],
            result["failed"],
        )

        # Log details for each fax processed
        for detail in result.get("details", []):
            if detail["status"] == "filed":
                logger.info(
                    "  Filed fax %s -> patient %s as '%s' (assigned to physician %s)",
                    detail.get("fax_id"),
                    detail.get("patient_name"),
                    detail.get("document_type"),
                    detail.get("physician_id"),
                )
            elif detail["status"] == "skipped":
                logger.info(
                    "  Skipped fax %s: %s",
                    detail.get("fax_id"),
                    detail.get("reason"),
                )
            else:
                logger.warning(
                    "  Failed fax %s: %s",
                    detail.get("fax_id"),
                    detail.get("reason"),
                )

    except Exception:
        logger.exception("Fax inbox processing encountered an unexpected error")


def run_once():
    """Run all steps immediately (for testing or manual execution)."""
    logger.info("Running in single-execution mode")

    if "--fax-only" in sys.argv:
        logger.info("Running fax filing only")
        process_fax_inbox()
        return

    fetch_and_generate()
    if _daily_summary_path:
        send_summary()
    else:
        logger.error("No summary generated, skipping send")

    process_fax_inbox()


def main():
    """Start the scheduler with the configured timezone and job times."""
    if "--run-once" in sys.argv:
        run_once()
        return

    tz = pytz.timezone(ScheduleConfig.TIMEZONE)
    scheduler = BlockingScheduler(timezone=tz)

    # ── Daily Summary Jobs ─────────────────────────────────────────
    scheduler.add_job(
        fetch_and_generate,
        "cron",
        hour=ScheduleConfig.FETCH_HOUR,
        minute=ScheduleConfig.FETCH_MINUTE,
        id="fetch_appointments",
        name="Fetch appointments and generate summary (12:01 AM)",
        misfire_grace_time=300,
    )

    scheduler.add_job(
        send_summary,
        "cron",
        hour=ScheduleConfig.SEND_HOUR,
        minute=ScheduleConfig.SEND_MINUTE,
        id="send_summary",
        name="Send summary via Spruce (7:00 AM)",
        misfire_grace_time=300,
    )

    # ── Fax Filing Jobs ────────────────────────────────────────────
    # Monday through Thursday: every hour from 7 AM to 4 PM (on the hour)
    scheduler.add_job(
        process_fax_inbox,
        "cron",
        day_of_week="mon-thu",
        hour=ScheduleConfig.FAX_MON_THU_HOURS,
        minute=0,
        id="fax_filing_mon_thu",
        name="File faxes to patient charts (Mon-Thu 7AM-4PM)",
        misfire_grace_time=300,
    )

    # Friday: every hour from 7 AM to 11 AM (on the hour)
    scheduler.add_job(
        process_fax_inbox,
        "cron",
        day_of_week="fri",
        hour=ScheduleConfig.FAX_FRI_HOURS,
        minute=0,
        id="fax_filing_fri",
        name="File faxes to patient charts (Fri 7AM-11AM)",
        misfire_grace_time=300,
    )

    logger.info(
        "Scheduler started. Fetch at %02d:%02d, Send at %02d:%02d (%s)",
        ScheduleConfig.FETCH_HOUR,
        ScheduleConfig.FETCH_MINUTE,
        ScheduleConfig.SEND_HOUR,
        ScheduleConfig.SEND_MINUTE,
        ScheduleConfig.TIMEZONE,
    )
    logger.info(
        "Fax filing: Mon-Thu hourly %s, Fri hourly %s",
        ScheduleConfig.FAX_MON_THU_HOURS,
        ScheduleConfig.FAX_FRI_HOURS,
    )
    logger.info("Press Ctrl+C to exit")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shut down")


if __name__ == "__main__":
    main()
