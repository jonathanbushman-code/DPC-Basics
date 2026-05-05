"""Scheduled agents for DPC-Basics.

Daily clinical analytics:
1. 12:01 AM - fetch today's appointments from Elation, generate the summary
2. 7:00 AM  - send the summary to a Spruce conversation

Weekly SPRUS dashboard:
3. Mon 7:00 AM (configurable) - pull last 7 days of Spruce call/SMS activity,
   render a per-phone + per-provider report with an hourly call-volume chart,
   and deliver it to a Spruce conversation.
"""

import logging
import os
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config import ScheduleConfig, WeeklyReportConfig
from services.appointment_service import AppointmentService
from services.analytics_service import AnalyticsService
from services.notification_service import NotificationService
from services.weekly_report_service import WeeklyReportService

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


def run_weekly_report():
    """Weekly job: SPRUS call/SMS dashboard for the previous 7 days."""
    logger.info("=== Starting SPRUS weekly report ===")
    try:
        WeeklyReportService().run(send=True)
        logger.info("Weekly report delivered")
    except Exception:
        logger.exception("Failed to generate or deliver weekly report")


def run_once():
    """Run both daily steps immediately (for testing or manual execution)."""
    logger.info("Running daily flow in single-execution mode")
    fetch_and_generate()
    if _daily_summary_path:
        send_summary()
    else:
        logger.error("No summary generated, skipping send")


def main():
    """Start the scheduler with the configured timezone and job times."""
    if "--run-once" in sys.argv:
        run_once()
        return
    if "--weekly-once" in sys.argv:
        # Render and deliver the weekly report immediately
        run_weekly_report()
        return
    if "--weekly-dry-run" in sys.argv:
        # Render the weekly report but do not deliver it
        WeeklyReportService().run(send=False)
        return

    tz = pytz.timezone(ScheduleConfig.TIMEZONE)
    scheduler = BlockingScheduler(timezone=tz)

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

    scheduler.add_job(
        run_weekly_report,
        "cron",
        day_of_week=WeeklyReportConfig.DAY_OF_WEEK,
        hour=WeeklyReportConfig.HOUR,
        minute=WeeklyReportConfig.MINUTE,
        id="weekly_sprus_report",
        name="SPRUS weekly call/SMS dashboard",
        misfire_grace_time=600,
    )

    logger.info(
        "Scheduler started. Daily: fetch %02d:%02d, send %02d:%02d. "
        "Weekly: %s %02d:%02d (%s)",
        ScheduleConfig.FETCH_HOUR,
        ScheduleConfig.FETCH_MINUTE,
        ScheduleConfig.SEND_HOUR,
        ScheduleConfig.SEND_MINUTE,
        WeeklyReportConfig.DAY_OF_WEEK,
        WeeklyReportConfig.HOUR,
        WeeklyReportConfig.MINUTE,
        ScheduleConfig.TIMEZONE,
    )
    logger.info("Press Ctrl+C to exit")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shut down")


if __name__ == "__main__":
    main()
