"""Twilio call handler — generates TwiML responses for voice webhooks.

Twilio sends HTTP requests to our server at various stages of a call.
This module builds the TwiML XML responses that tell Twilio what to do:
greet the caller, gather speech, speak the AI response, loop, and
handle call completion.
"""

import logging

from twilio.twiml.voice_response import Gather, VoiceResponse

from voice_assistant.config import TwilioConfig, VoiceAssistantConfig
from voice_assistant.conversation_engine import ConversationEngine, sessions
from voice_assistant.prompts import GREETING
from voice_assistant.spruce_logger import SpruceCallLogger

logger = logging.getLogger(__name__)

# Shared engine and logger instances
engine = ConversationEngine()
spruce_logger = SpruceCallLogger()


def handle_incoming_call(call_sid: str, caller_number: str) -> str:
    """Handle a new incoming call — greet and start listening.

    Creates a new call session, speaks the greeting, and opens a
    speech-gathering loop.

    Args:
        call_sid: Twilio CallSid for this call.
        caller_number: The caller's phone number (E.164).

    Returns:
        TwiML XML string.
    """
    sessions.create(call_sid, caller_number)

    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{VoiceAssistantConfig.WEBHOOK_BASE_URL}/voice/respond",
        method="POST",
        speech_timeout=TwilioConfig.SPEECH_TIMEOUT,
        language=TwilioConfig.SPEECH_LANGUAGE,
        timeout=TwilioConfig.GATHER_TIMEOUT,
    )
    gather.say(GREETING, voice=TwilioConfig.TTS_VOICE)
    response.append(gather)

    # If caller doesn't say anything, prompt them
    response.say(
        "I didn't catch that. How can I help you today?",
        voice=TwilioConfig.TTS_VOICE,
    )
    response.redirect(
        f"{VoiceAssistantConfig.WEBHOOK_BASE_URL}/voice/respond-silence",
        method="POST",
    )

    logger.info("Incoming call %s from %s — greeting sent", call_sid, caller_number)
    return str(response)


def handle_caller_speech(call_sid: str, speech_result: str) -> str:
    """Process transcribed caller speech and respond with AI-generated text.

    Args:
        call_sid: Twilio CallSid.
        speech_result: The STT transcription from Twilio.

    Returns:
        TwiML XML string.
    """
    if not speech_result or not speech_result.strip():
        return handle_silence(call_sid)

    # Get AI response
    assistant_text = engine.respond(call_sid, speech_result.strip())

    session = sessions.get(call_sid)

    response = VoiceResponse()

    # If the assistant requested a transfer, connect to staff
    if session and session.transfer_requested:
        response.say(assistant_text, voice=TwilioConfig.TTS_VOICE)
        if TwilioConfig.STAFF_PHONE_NUMBER:
            response.dial(TwilioConfig.STAFF_PHONE_NUMBER)
        else:
            response.say(
                "I'm sorry, I'm unable to complete the transfer right now. "
                "A team member will call you back shortly.",
                voice=TwilioConfig.TTS_VOICE,
            )
            response.hangup()
        return str(response)

    # Normal flow: speak the response and listen for more input
    gather = Gather(
        input="speech",
        action=f"{VoiceAssistantConfig.WEBHOOK_BASE_URL}/voice/respond",
        method="POST",
        speech_timeout=TwilioConfig.SPEECH_TIMEOUT,
        language=TwilioConfig.SPEECH_LANGUAGE,
        timeout=TwilioConfig.GATHER_TIMEOUT,
    )
    gather.say(assistant_text, voice=TwilioConfig.TTS_VOICE)
    response.append(gather)

    # Silence fallback
    response.redirect(
        f"{VoiceAssistantConfig.WEBHOOK_BASE_URL}/voice/respond-silence",
        method="POST",
    )

    return str(response)


def handle_silence(call_sid: str) -> str:
    """Handle when the caller is silent — re-prompt them.

    Args:
        call_sid: Twilio CallSid.

    Returns:
        TwiML XML string.
    """
    session = sessions.get(call_sid)

    response = VoiceResponse()

    # If no session or too many silent turns, end the call gracefully
    if session is None:
        response.say(
            "I'm sorry, it seems we've been disconnected. "
            "Please call back if you need assistance. Goodbye.",
            voice=TwilioConfig.TTS_VOICE,
        )
        response.hangup()
        return str(response)

    gather = Gather(
        input="speech",
        action=f"{VoiceAssistantConfig.WEBHOOK_BASE_URL}/voice/respond",
        method="POST",
        speech_timeout=TwilioConfig.SPEECH_TIMEOUT,
        language=TwilioConfig.SPEECH_LANGUAGE,
        timeout=TwilioConfig.GATHER_TIMEOUT,
    )
    gather.say(
        "Are you still there? I'm here to help whenever you're ready.",
        voice=TwilioConfig.TTS_VOICE,
    )
    response.append(gather)

    # If still no response, say goodbye
    response.say(
        "It seems like you may have stepped away. "
        "Feel free to call us back anytime. Goodbye!",
        voice=TwilioConfig.TTS_VOICE,
    )
    response.hangup()

    return str(response)


def handle_call_status(call_sid: str, call_status: str) -> None:
    """Handle Twilio call status callback (call completed/failed/etc.).

    When a call ends, generates a summary and posts it to Spruce so the
    care team can see what was discussed and follow up.

    Args:
        call_sid: Twilio CallSid.
        call_status: The Twilio call status (completed, busy, failed, etc.).
    """
    logger.info("Call %s status: %s", call_sid, call_status)

    if call_status not in ("completed", "busy", "no-answer", "failed", "canceled"):
        return

    session = sessions.get(call_sid)
    if session is None:
        logger.info("No session for ended call %s — nothing to log", call_sid)
        return

    # Only log calls that had at least one conversation turn
    if session.turn_count > 0:
        try:
            summary = engine.build_call_summary(call_sid)
            spruce_logger.log_call_summary(
                caller_number=session.caller_number,
                call_sid=call_sid,
                summary=summary,
                turn_count=session.turn_count,
                transfer_requested=session.transfer_requested,
            )
        except Exception:
            logger.exception("Failed to log call summary for %s", call_sid)

    # Clean up the session
    sessions.remove(call_sid)
    logger.info("Session cleaned up for call %s", call_sid)
