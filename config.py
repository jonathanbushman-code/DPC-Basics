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
    CONVERSATIONS_ENDPOINT = f"{BASE_URL}/v1/conversations"
    CONVERSATION_ITEMS_ENDPOINT = f"{BASE_URL}/v1/conversationItems"
    INTERNAL_ENDPOINTS_ENDPOINT = f"{BASE_URL}/v1/internalendpoints"


class ScheduleConfig:
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    FETCH_HOUR = int(os.getenv("FETCH_HOUR", "0"))
    FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "1"))
    SEND_HOUR = int(os.getenv("SEND_HOUR", "7"))
    SEND_MINUTE = int(os.getenv("SEND_MINUTE", "0"))
    WEEKLY_REPORT_DAY = os.getenv("WEEKLY_REPORT_DAY", "mon")
    WEEKLY_REPORT_HOUR = int(os.getenv("WEEKLY_REPORT_HOUR", "7"))
    WEEKLY_REPORT_MINUTE = int(os.getenv("WEEKLY_REPORT_MINUTE", "30"))


class BusinessHoursConfig:
    """Business hours in Central Standard Time for missed-call tracking.

    Mon-Thu: 8:00 AM - 5:00 PM with a lunch break 12:00 - 1:00 PM
    Friday:  8:00 AM - 12:00 PM (no afternoon)
    """
    TIMEZONE = "America/Chicago"
    # Monday=0 .. Friday=4
    MON_THU_START = 8   # 8 AM
    MON_THU_END = 17    # 5 PM
    LUNCH_START = 12     # 12 PM
    LUNCH_END = 13       # 1 PM
    FRIDAY_START = 8     # 8 AM
    FRIDAY_END = 12      # 12 PM


SUMMARY_OUTPUT_DIR = os.getenv("SUMMARY_OUTPUT_DIR", "./output")
