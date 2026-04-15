"""FastAPI webhook server for the voice assistant.

Exposes endpoints that Twilio calls during the lifecycle of a phone call:
  POST /voice/incoming       — New incoming call (returns greeting TwiML)
  POST /voice/respond        — Caller spoke (returns AI response TwiML)
  POST /voice/respond-silence — Caller was silent (re-prompts)
  POST /voice/status         — Call status changed (logs summary to Spruce)
  GET  /health               — Health check
"""

import logging

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import PlainTextResponse

from voice_assistant.call_handler import (
    handle_call_status,
    handle_caller_speech,
    handle_incoming_call,
    handle_silence,
)
from voice_assistant.config import TwilioConfig, VoiceAssistantConfig

logger = logging.getLogger(__name__)

app = FastAPI(
    title="DPC Voice Assistant",
    description="AI-powered phone assistant for the practice, integrated with Spruce Health",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Twilio request validation
# ---------------------------------------------------------------------------

def _validate_twilio_signature(request: Request, body: bytes) -> bool:
    """Validate that the request genuinely came from Twilio.

    Uses HMAC-SHA1 signature validation with the Twilio auth token.
    Disabled when auth token is not configured (development mode).
    """
    auth_token = TwilioConfig.AUTH_TOKEN
    if not auth_token:
        # No auth token configured — skip validation (dev mode)
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    # Reconstruct the full URL Twilio used to sign the request
    url = str(request.url)

    from twilio.request_validator import RequestValidator
    validator = RequestValidator(auth_token)

    # For POST requests, Twilio signs against the form parameters
    # We need to parse them from the body
    params = {}
    if body:
        from urllib.parse import parse_qs
        parsed = parse_qs(body.decode("utf-8"))
        params = {k: v[0] for k, v in parsed.items()}

    return validator.validate(url, params, signature)


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@app.post("/voice/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(""),
    From: str = Form(""),
):
    """Handle a new incoming phone call.

    Twilio POSTs here when a call arrives on the configured number.
    We greet the caller and start listening for speech.
    """
    twiml = handle_incoming_call(call_sid=CallSid, caller_number=From)
    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/respond")
async def voice_respond(
    request: Request,
    CallSid: str = Form(""),
    SpeechResult: str = Form(""),
):
    """Handle transcribed caller speech.

    Twilio POSTs the speech-to-text result here after the caller speaks.
    We pass it through the Claude conversation engine and return the
    AI response as TwiML.
    """
    twiml = handle_caller_speech(call_sid=CallSid, speech_result=SpeechResult)
    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/respond-silence")
async def voice_respond_silence(
    request: Request,
    CallSid: str = Form(""),
):
    """Handle caller silence — re-prompt or end the call."""
    twiml = handle_silence(call_sid=CallSid)
    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/status")
async def voice_status(
    request: Request,
    CallSid: str = Form(""),
    CallStatus: str = Form(""),
):
    """Handle Twilio call status callbacks.

    Twilio POSTs here when the call status changes (ringing, in-progress,
    completed, etc.).  When a call ends, we generate a summary and post
    it to Spruce for the care team.
    """
    handle_call_status(call_sid=CallSid, call_status=CallStatus)
    return PlainTextResponse("OK")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "dpc-voice-assistant",
        "practice": VoiceAssistantConfig.PRACTICE_NAME,
    }


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    logger.info(
        "Voice assistant server started — practice: %s, port: %d",
        VoiceAssistantConfig.PRACTICE_NAME,
        VoiceAssistantConfig.PORT,
    )
    logger.info(
        "Webhook base URL: %s",
        VoiceAssistantConfig.WEBHOOK_BASE_URL,
    )


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Voice assistant server shutting down")
