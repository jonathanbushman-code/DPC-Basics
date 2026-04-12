"""Daily Clinical Analytics Summary Agent.

This agent runs on a schedule to:
1. Fetch today's appointments from Elation Health at 12:01 AM
2. Generate a clinical analytics summary PDF
3. Send the summary to a specific Spruce Health user at 7:00 AM
4. Poll for checked-out appointments and send Google review requests via SMS
"""

import logging
import os
import sys
from datetime import datetime

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config import ScheduleConfig, SUMMARY_OUTPUT_DIR
from services.appointment_service import AppointmentService
from services.analytics_service import AnalyticsService
from services.notification_service import NotificationService
from services.review_request_service import ReviewRequestService

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


def check_checkouts_and_send_reviews():
    """Interval job: Poll for checked-out appointments and send review requests.

    Runs every N minutes during business hours. Detects appointments that
    have transitioned to 'Checked Out' status and sends each patient a
    thank-you SMS with a Google review link via Spruce.
    """
    # Only run during configured business hours
    tz = pytz.timezone(ScheduleConfig.TIMEZONE)
    now_local = datetime.now(tz)
    if not (
        ScheduleConfig.CHECKOUT_POLL_START_HOUR
        <= now_local.hour
        < ScheduleConfig.CHECKOUT_POLL_END_HOUR
    ):
        logger.debug(
            "Outside business hours (%02d:00-%02d:00), skipping checkout poll",
            ScheduleConfig.CHECKOUT_POLL_START_HOUR,
            ScheduleConfig.CHECKOUT_POLL_END_HOUR,
        )
        return

    logger.info("--- Checking for new checked-out appointments ---")
    try:
        review_service = ReviewRequestService()
        sent = review_service.process_checked_out_appointments()
        if sent:
            logger.info("Sent %d review request(s)", sent)
        else:
            logger.debug("No new review requests to send")
    except Exception:
        logger.exception("Error in checkout review request polling")


def run_once():
    """Run both steps immediately (for testing or manual execution)."""
    logger.info("Running in single-execution mode")
    fetch_and_generate()
    if _daily_summary_path:
        send_summary()
    else:
        logger.error("No summary generated, skipping send")
    # Also run a single checkout review check
    check_checkouts_and_send_reviews()


def main():
    """Start the scheduler with the configured timezone and job times."""
    if "--run-once" in sys.argv:
        run_once()
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
        check_checkouts_and_send_reviews,
        "interval",
        minutes=ScheduleConfig.CHECKOUT_POLL_INTERVAL_MINUTES,
        id="checkout_review_poll",
        name=(
            f"Poll for checkouts every "
            f"{ScheduleConfig.CHECKOUT_POLL_INTERVAL_MINUTES}min "
            f"({ScheduleConfig.CHECKOUT_POLL_START_HOUR}:00-"
            f"{ScheduleConfig.CHECKOUT_POLL_END_HOUR}:00)"
        ),
        misfire_grace_time=120,
    )

    logger.info(
        "Scheduler started. Fetch at %02d:%02d, Send at %02d:%02d, "
        "Checkout poll every %d min (%02d:00-%02d:00) (%s)",
        ScheduleConfig.FETCH_HOUR,
        ScheduleConfig.FETCH_MINUTE,
        ScheduleConfig.SEND_HOUR,
        ScheduleConfig.SEND_MINUTE,
        ScheduleConfig.CHECKOUT_POLL_INTERVAL_MINUTES,
        ScheduleConfig.CHECKOUT_POLL_START_HOUR,
        ScheduleConfig.CHECKOUT_POLL_END_HOUR,
        ScheduleConfig.TIMEZONE,
    )
    logger.info("Press Ctrl+C to exit")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shut down")


if __name__ == "__main__":
    main()
