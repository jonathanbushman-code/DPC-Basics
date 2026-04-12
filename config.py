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
    RECEIVED_FAXES_ENDPOINT = f"{BASE_URL}/received_faxes/"
    DOCUMENTS_ENDPOINT = f"{BASE_URL}/documents/"
    PRACTICES_ENDPOINT = f"{BASE_URL}/practices/"


class SpruceConfig:
    API_TOKEN = os.getenv("SPRUCE_API_TOKEN", "")
    BASE_URL = os.getenv("SPRUCE_API_BASE_URL", "https://api.sprucehealth.com")
    CONVERSATION_ID = os.getenv("SPRUCE_CONVERSATION_ID", "")
    UPLOAD_MEDIA_ENDPOINT = f"{BASE_URL}/v1/media"
    POST_MESSAGE_ENDPOINT = f"{BASE_URL}/v1/conversations/{CONVERSATION_ID}/messages"


class ScheduleConfig:
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    FETCH_HOUR = int(os.getenv("FETCH_HOUR", "0"))
    FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "1"))
    SEND_HOUR = int(os.getenv("SEND_HOUR", "7"))
    SEND_MINUTE = int(os.getenv("SEND_MINUTE", "0"))

    # Fax filing schedule: Mon-Thu 7am-4pm, Fri 7am-11am (hourly on the hour)
    FAX_MON_THU_HOURS = os.getenv("FAX_MON_THU_HOURS", "7-16")
    FAX_FRI_HOURS = os.getenv("FAX_FRI_HOURS", "7-11")


SUMMARY_OUTPUT_DIR = os.getenv("SUMMARY_OUTPUT_DIR", "./output")
