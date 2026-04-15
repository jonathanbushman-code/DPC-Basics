"""Configuration for the voice assistant subsystem."""

import os

from dotenv import load_dotenv

load_dotenv()


class TwilioConfig:
    """Twilio telephony credentials and settings."""

    ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

    # TTS voice — Twilio supports Polly voices for natural speech
    TTS_VOICE = os.getenv("TWILIO_TTS_VOICE", "Polly.Joanna-Neural")

    # Speech recognition settings
    SPEECH_TIMEOUT = os.getenv("TWILIO_SPEECH_TIMEOUT", "auto")
    SPEECH_LANGUAGE = os.getenv("TWILIO_SPEECH_LANGUAGE", "en-US")

    # Maximum seconds a caller can speak per turn
    GATHER_TIMEOUT = int(os.getenv("TWILIO_GATHER_TIMEOUT", "3"))

    # Staff phone number to transfer calls to when human is needed
    STAFF_PHONE_NUMBER = os.getenv("STAFF_PHONE_NUMBER", "")


class AnthropicConfig:
    """Anthropic Claude API settings for conversation intelligence."""

    API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL = os.getenv("VOICE_ASSISTANT_MODEL", "claude-sonnet-4-20250514")
    MAX_TOKENS = int(os.getenv("VOICE_ASSISTANT_MAX_TOKENS", "300"))
    TEMPERATURE = float(os.getenv("VOICE_ASSISTANT_TEMPERATURE", "0.3"))


class VoiceAssistantConfig:
    """General voice assistant settings."""

    # Practice details used in the assistant's personality
    PRACTICE_NAME = os.getenv("PRACTICE_NAME", "our practice")
    PRACTICE_PHONE = os.getenv("PRACTICE_PHONE", "")
    PRACTICE_ADDRESS = os.getenv("PRACTICE_ADDRESS", "")
    PRACTICE_HOURS = os.getenv(
        "PRACTICE_HOURS",
        "Monday through Friday, 8 AM to 5 PM",
    )

    # Spruce conversation for logging call summaries
    SPRUCE_VOICE_LOG_CONVERSATION_ID = os.getenv(
        "SPRUCE_VOICE_LOG_CONVERSATION_ID", ""
    )

    # Webhook base URL (where Twilio can reach this server)
    WEBHOOK_BASE_URL = os.getenv("VOICE_WEBHOOK_BASE_URL", "http://localhost:8000")

    # Server settings
    HOST = os.getenv("VOICE_SERVER_HOST", "0.0.0.0")
    PORT = int(os.getenv("VOICE_SERVER_PORT", "8000"))

    # Maximum conversation turns before suggesting transfer to staff
    MAX_TURNS = int(os.getenv("VOICE_MAX_TURNS", "20"))
