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
    WEBHOOK_SECRET = os.getenv("SPRUCE_WEBHOOK_SECRET", "")
    WEBHOOKS_ENDPOINT = f"{BASE_URL}/v1/webhooks/endpoints"


class ChatbotConfig:
    ENABLED = os.getenv("CHATBOT_ENABLED", "true").lower() == "true"
    WEBHOOK_PORT = int(os.getenv("CHATBOT_WEBHOOK_PORT", "8080"))
    WEBHOOK_HOST = os.getenv("CHATBOT_WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PATH = os.getenv("CHATBOT_WEBHOOK_PATH", "/webhook/spruce")
    PUBLIC_URL = os.getenv("CHATBOT_PUBLIC_URL", "")
    ESCALATION_CONVERSATION_ID = os.getenv(
        "SPRUCE_ESCALATION_CONVERSATION_ID", ""
    )
    PRACTICE_PHONE = os.getenv("PRACTICE_PHONE", "(580) 599-0272")
    PRACTICE_NAME = os.getenv("PRACTICE_NAME", "Reliant Direct Primary Care")


class ScheduleConfig:
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    FETCH_HOUR = int(os.getenv("FETCH_HOUR", "0"))
    FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "1"))
    SEND_HOUR = int(os.getenv("SEND_HOUR", "7"))
    SEND_MINUTE = int(os.getenv("SEND_MINUTE", "0"))


SUMMARY_OUTPUT_DIR = os.getenv("SUMMARY_OUTPUT_DIR", "./output")
