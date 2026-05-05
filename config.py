import os
from dotenv import load_dotenv

load_dotenv()


class ElationConfig:
    CLIENT_ID = os.getenv("ELATION_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("ELATION_CLIENT_SECRET", "")
    BASE_URL = os.getenv("ELATION_API_BASE_URL", "https://sandbox.elationemr.com/api/2.0")
    TOKEN_ENDPOINT = f"{BASE_URL}/oauth2/token/"
    APPOINTMENTS_ENDPOINT = f"{BASE_URL}/appointments/"
    PATIENTS_ENDPOINT = f"{BASE_URL}/patients/"
    PHYSICIANS_ENDPOINT = f"{BASE_URL}/physicians/"


class SpruceConfig:
    API_TOKEN = os.getenv("SPRUCE_API_TOKEN", "")
    BASE_URL = os.getenv("SPRUCE_API_BASE_URL", "https://api.sprucehealth.com")
    CONVERSATION_ID = os.getenv("SPRUCE_CONVERSATION_ID", "")
    UPLOAD_MEDIA_ENDPOINT = f"{BASE_URL}/v1/media"
    POST_MESSAGE_ENDPOINT = f"{BASE_URL}/v1/conversations/{CONVERSATION_ID}/messages"
    # Reporting endpoints (Spruce telephony + messaging activity)
    CALLS_ENDPOINT = os.getenv("SPRUCE_CALLS_ENDPOINT", f"{BASE_URL}/v1/calls")
    MESSAGES_ENDPOINT = os.getenv("SPRUCE_MESSAGES_ENDPOINT", f"{BASE_URL}/v1/messages")
    PHONE_NUMBERS_ENDPOINT = os.getenv(
        "SPRUCE_PHONE_NUMBERS_ENDPOINT", f"{BASE_URL}/v1/phone_numbers"
    )


class ScheduleConfig:
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    FETCH_HOUR = int(os.getenv("FETCH_HOUR", "0"))
    FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "1"))
    SEND_HOUR = int(os.getenv("SEND_HOUR", "7"))
    SEND_MINUTE = int(os.getenv("SEND_MINUTE", "0"))


class WeeklyReportConfig:
    """Settings for the SPRUS weekly call/SMS dashboard."""

    # Cron parts for weekly delivery (defaults: Monday 7:00 local time)
    DAY_OF_WEEK = os.getenv("WEEKLY_REPORT_DAY", "mon")
    HOUR = int(os.getenv("WEEKLY_REPORT_HOUR", "7"))
    MINUTE = int(os.getenv("WEEKLY_REPORT_MINUTE", "0"))
    # Where to deliver. Falls back to the daily-summary conversation if unset.
    CONVERSATION_ID = os.getenv("WEEKLY_REPORT_CONVERSATION_ID", "") or os.getenv(
        "SPRUCE_CONVERSATION_ID", ""
    )
    # Optional JSON file mapping phone IDs -> {"name": "...", "employee": "..."}
    PHONE_MAPPING_FILE = os.getenv("PHONE_MAPPING_FILE", "phone_mapping.json")
    # Whether to enrich call/SMS records with Elation provider info per patient
    ENRICH_PROVIDERS = os.getenv("WEEKLY_REPORT_ENRICH_PROVIDERS", "true").lower() in (
        "1",
        "true",
        "yes",
    )


SUMMARY_OUTPUT_DIR = os.getenv("SUMMARY_OUTPUT_DIR", "./output")
