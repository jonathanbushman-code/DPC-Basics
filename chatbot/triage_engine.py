"""Medical triage engine for the Reliant DPC chatbot.

Classifies incoming patient messages by urgency and determines whether
the chatbot can respond automatically or must escalate to a human provider.

Triage levels:
    EMERGENCY  - Call 911 immediately (chest pain, stroke symptoms, etc.)
    URGENT     - Escalate to provider now (needs same-day clinical attention)
    MODERATE   - Escalate to provider (medical question requiring clinical input)
    LOW        - Chatbot can handle (general info, scheduling, membership Q&A)
"""

import re
from dataclasses import dataclass
from enum import IntEnum

from config import ChatbotConfig


class TriageLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    URGENT = 2
    EMERGENCY = 3


@dataclass
class TriageResult:
    level: TriageLevel
    matched_category: str
    auto_response: str | None  # Pre-built response for EMERGENCY level
    should_escalate: bool


# ---------------------------------------------------------------------------
# Pattern definitions for each triage level
# ---------------------------------------------------------------------------

# EMERGENCY: Life-threatening — tell patient to call 911
EMERGENCY_PATTERNS = [
    (r"\b(chest pain|chest tight|pressure in.*(chest|heart))\b", "chest_pain"),
    (r"\b(can.?t breathe|trouble breathing|shortness of breath|breathing difficulty|gasping)\b", "breathing_difficulty"),
    (r"\b(stroke|face droop|arm weak|slurred speech|sudden numbness)\b", "stroke_symptoms"),
    (r"\b(unconscious|passed out|unresponsive|not breathing|no pulse)\b", "unresponsive"),
    (r"\b(overdose|took too (many|much)|poison|swallow)\b", "overdose_poisoning"),
    (r"\b(suicid|kill (my|him|her|them)self|want to die|end (my|it all)|self.?harm)\b", "suicide_self_harm"),
    (r"\b(severe bleed|won.?t stop bleeding|arterial|hemorrhag)\b", "severe_bleeding"),
    (r"\b(seizure|convuls)\b", "seizure"),
    (r"\b(anaphyla|throat.*(swell|clos)|epipen|can.?t swallow.*swell)\b", "anaphylaxis"),
    (r"\b(heart attack|cardiac arrest)\b", "cardiac"),
    (r"\b(severe allergic|allergic reaction.*severe)\b", "severe_allergic_reaction"),
    (r"\b(gun.?shot|stab wound|impaled)\b", "traumatic_injury"),
]

# URGENT: Needs provider attention today
URGENT_PATTERNS = [
    (r"\b(high fever|fever.*(over|above)\s*(102|103|104|105)|temp.*(102|103|104|105))\b", "high_fever"),
    (r"\b(severe pain|worst pain|unbearable|excruciating|pain.*10(/|\s*out))\b", "severe_pain"),
    (r"\b(blood in (urine|stool|vomit)|vomiting blood|coughing.*blood)\b", "blood_in_fluids"),
    (r"\b(broken bone|fracture|dislocat)\b", "fracture"),
    (r"\b(head injury|concussion|hit.*(my|his|her) head)\b", "head_injury"),
    (r"\b(deep cut|lacerat|need.*(stitch|suture))\b", "laceration"),
    (r"\b(sudden.*(vision|blind|deaf|hearing)|lost.*(vision|sight))\b", "sudden_sensory_loss"),
    (r"\b(severe vomit|can.?t keep (anything|food|water) down|dehydrat)\b", "dehydration_vomiting"),
    (r"\b(swollen.*(red|hot|warm).*joint|joint.*swollen.*(red|hot))\b", "joint_infection_signs"),
    (r"\b(pregnant|pregnancy).*(bleed|cramp|pain|emergency)\b", "pregnancy_complication"),
    (r"\b(diabetic|blood sugar).*(very (high|low)|emergency|danger)\b", "diabetic_emergency"),
    (r"\b(burn.*(large|severe|third|second))\b", "severe_burn"),
    (r"\b(animal bite|dog bite|cat bite|bitten)\b", "animal_bite"),
    (r"\b(allergic reaction|hives.*spread|swelling.*face)\b", "allergic_reaction"),
]

# MODERATE: Medical question that needs a provider but not same-day urgent
MODERATE_PATTERNS = [
    (r"\b(symptom|feeling (sick|ill|unwell|bad)|not feeling (well|good))\b", "general_symptoms"),
    (r"\b(fever|temperature|chills)\b", "fever"),
    (r"\b(cough|sore throat|congestion|runny nose|sinus|cold|flu)\b", "respiratory_symptoms"),
    (r"\b(rash|hives|itchy|itch|skin.*(problem|issue|concern))\b", "skin_concern"),
    (r"\b(headache|migraine)\b", "headache"),
    (r"\b(back pain|neck pain|shoulder pain|knee pain|joint pain)\b", "musculoskeletal_pain"),
    (r"\b(stomach|nausea|vomit|diarrhea|constipat|digest)\b", "gi_symptoms"),
    (r"\b(dizzy|lightheaded|vertigo|faint)\b", "dizziness"),
    (r"\b(anxiety|depress|mental health|stress|panic|mood)\b", "mental_health"),
    (r"\b(uti|urinary|burning.*(urinat|pee)|frequent.*(urinat|pee))\b", "urinary_symptoms"),
    (r"\b(ear.?(ache|infection|pain)|ear.*hurt)\b", "ear_issue"),
    (r"\b(eye.*(red|pink|pain|infect)|pink.?eye|conjunctiv)\b", "eye_issue"),
    (r"\b(lump|bump|mass|growth|swelling|swollen)\b", "lump_or_swelling"),
    (r"\b(tired|fatigue|exhaust|no energy|lethargi)\b", "fatigue"),
    (r"\b(insomnia|can.?t sleep|sleep.*(trouble|problem|issue))\b", "sleep_issue"),
    (r"\b(weight.*(gain|loss|change)|losing weight|gaining weight)\b", "weight_change"),
    (r"\b(blood pressure|hypertension|bp)\b", "blood_pressure"),
    (r"\b(diabetes|blood sugar|glucose|a1c)\b", "diabetes"),
    (r"\b(asthma|inhaler|wheez)\b", "asthma"),
    (r"\b(hurt|pain|ache|sore|tender|discomfort)\b", "general_pain"),
    (r"\b(sick|ill|unwell|worse|worsening|getting worse)\b", "general_illness"),
    (r"\b(medicine|medication|side effect|drug|dosage|dose)\b", "medication_question"),
    (r"\b(diagnos|condition|disease)\b", "diagnosis_question"),
]

# ---------------------------------------------------------------------------
# Emergency auto-responses
# ---------------------------------------------------------------------------

EMERGENCY_RESPONSES = {
    "chest_pain": (
        "I'm concerned about your symptoms. Chest pain can be a sign of a "
        "serious medical emergency.\n\n"
        "**Please call 911 immediately** if you are experiencing chest pain, "
        "tightness, or pressure.\n\n"
        "A member of our care team has been notified and will follow up with you."
    ),
    "breathing_difficulty": (
        "Difficulty breathing can be a medical emergency.\n\n"
        "**If you are having severe trouble breathing, please call 911 "
        "immediately.**\n\n"
        "A member of our care team has been notified and will reach out to you."
    ),
    "stroke_symptoms": (
        "The symptoms you're describing could indicate a stroke. Remember "
        "**FAST**:\n"
        "- **F**ace drooping\n"
        "- **A**rm weakness\n"
        "- **S**peech difficulty\n"
        "- **T**ime to call 911\n\n"
        "**Please call 911 immediately.** Every minute counts.\n\n"
        "Our care team has been notified."
    ),
    "unresponsive": (
        "**This is a medical emergency. Please call 911 immediately.**\n\n"
        "If someone is unresponsive or not breathing, call 911 and begin "
        "CPR if you are trained to do so.\n\n"
        "Our care team has been notified."
    ),
    "overdose_poisoning": (
        "**If you suspect an overdose or poisoning, call 911 immediately.**\n\n"
        "You can also call Poison Control at **1-800-222-1222**.\n\n"
        "Our care team has been notified and will follow up."
    ),
    "suicide_self_harm": (
        "I hear you, and I want you to know that help is available right now.\n\n"
        "**If you or someone you know is in immediate danger, please call 911.**\n\n"
        "You can also reach the **988 Suicide & Crisis Lifeline** by calling "
        "or texting **988** - available 24/7.\n\n"
        "Our care team has been notified and will reach out to you as soon "
        "as possible. You are not alone."
    ),
    "severe_bleeding": (
        "**If you are experiencing severe or uncontrolled bleeding, call 911 "
        "immediately.**\n\n"
        "While waiting for help, apply firm pressure to the wound with a "
        "clean cloth.\n\n"
        "Our care team has been notified."
    ),
    "seizure": (
        "**If someone is actively having a seizure or has had one, please "
        "call 911.**\n\n"
        "Keep the person safe, do not restrain them, and do not put anything "
        "in their mouth.\n\n"
        "Our care team has been notified."
    ),
    "anaphylaxis": (
        "**Throat swelling or anaphylaxis is a life-threatening emergency. "
        "Call 911 immediately.**\n\n"
        "If an EpiPen is available, use it now.\n\n"
        "Our care team has been notified."
    ),
    "cardiac": (
        "**A heart attack or cardiac event is a medical emergency. "
        "Call 911 immediately.**\n\n"
        "While waiting: sit or lie down, chew an aspirin if available and "
        "not allergic, and stay calm.\n\n"
        "Our care team has been notified."
    ),
    "severe_allergic_reaction": (
        "**A severe allergic reaction is a medical emergency. "
        "Call 911 immediately.**\n\n"
        "If an EpiPen is available, use it now. Our care team has been notified."
    ),
    "traumatic_injury": (
        "**This sounds like a serious injury. Please call 911 immediately.**\n\n"
        "Apply pressure to any bleeding wounds and try to stay still until "
        "help arrives.\n\n"
        "Our care team has been notified."
    ),
}

URGENT_AUTO_RESPONSE = (
    "Based on what you've described, I want to make sure you get prompt "
    "medical attention. I'm connecting you with a member of our care team "
    "right now.\n\n"
    "If your symptoms worsen or you feel this is a medical emergency, "
    "please call 911 or go to your nearest emergency room.\n\n"
    "In the meantime, you can also reach us directly at {phone}."
)

MODERATE_AUTO_RESPONSE = (
    "Thank you for reaching out about your health concern. I want to make "
    "sure you get the right guidance from your care team.\n\n"
    "I'm connecting you with a provider who can help. A member of our team "
    "will follow up with you shortly.\n\n"
    "If your symptoms become severe or you feel this is an emergency, "
    "please call 911 or go to your nearest emergency room.\n\n"
    "You can also reach us directly at {phone}."
)


def _fill_practice_placeholders(text: str) -> str:
    """Replace {phone} etc. with values from ChatbotConfig."""
    text = text.replace("{phone}", ChatbotConfig.PRACTICE_PHONE)
    text = text.replace("{practice_name}", ChatbotConfig.PRACTICE_NAME)
    return text


def assess(message: str) -> TriageResult:
    """Assess a patient message for medical urgency.

    Scans the message against emergency, urgent, and moderate patterns
    (in that priority order) and returns a TriageResult indicating the
    appropriate triage level and whether escalation is needed.
    """
    text = message.lower().strip()

    # Check emergency patterns first
    for pattern, category in EMERGENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return TriageResult(
                level=TriageLevel.EMERGENCY,
                matched_category=category,
                auto_response=EMERGENCY_RESPONSES.get(category, EMERGENCY_RESPONSES["unresponsive"]),
                should_escalate=True,
            )

    # Check urgent patterns
    for pattern, category in URGENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return TriageResult(
                level=TriageLevel.URGENT,
                matched_category=category,
                auto_response=_fill_practice_placeholders(URGENT_AUTO_RESPONSE),
                should_escalate=True,
            )

    # Check moderate patterns
    for pattern, category in MODERATE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return TriageResult(
                level=TriageLevel.MODERATE,
                matched_category=category,
                auto_response=_fill_practice_placeholders(MODERATE_AUTO_RESPONSE),
                should_escalate=True,
            )

    # No medical concern detected — safe for chatbot to handle
    return TriageResult(
        level=TriageLevel.LOW,
        matched_category="non_medical",
        auto_response=None,
        should_escalate=False,
    )
