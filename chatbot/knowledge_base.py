"""Knowledge base for the Reliant DPC chatbot.

Contains practice information, FAQs, and keyword-matching logic to
provide helpful responses to patient inquiries via Spruce messaging.
"""

import re

# ---------------------------------------------------------------------------
# Practice information sourced from www.reliantdpc.com
# ---------------------------------------------------------------------------

PRACTICE_INFO = {
    "name": "Reliant Direct Primary Care",
    "short_name": "Reliant DPC",
    "website": "www.reliantdpc.com",
    "email": "info@ReliantDPC.com",
    "phone": "(580) 599-0272",
    "model": "Direct Primary Care (DPC)",
    "sign_up_url": "https://www.reliantdpc.com/sign-up",
}

LOCATIONS = [
    {
        "name": "Enid",
        "address": "822 W Randolph Ave, Enid, OK",
        "providers": [
            "Dr. Sara Oldham",
            "Dr. Chuck Jantzen",
            "PA Riley Kline",
        ],
    },
    {
        "name": "Fairview",
        "address": "Fairview, OK",
        "providers": [
            "Dr. Andrea McEachern",
            "APRN Megan Ewing",
        ],
    },
    {
        "name": "Altus",
        "address": "Altus, OK",
        "providers": [
            "APRN Tiffany Forster",
        ],
    },
    {
        "name": "Cherokee",
        "address": "Cherokee, OK",
        "providers": [],
    },
]

MEMBERSHIP_BENEFITS = [
    "Unlimited office visits",
    "Discount prices on prescription medications",
    "Your doctor's cell phone number for direct access",
    "Same-day or next-day appointments",
    "Upfront, transparent pricing on medications, labs, and diagnostics",
    "Longer appointments with your provider",
    "Call, text, or email your doctor any time",
    "No insurance hassles or copays for primary care visits",
]

SERVICES = [
    "Annual physicals and wellness exams",
    "Acute illness visits (cold, flu, infections, etc.)",
    "Chronic disease management (diabetes, hypertension, asthma, etc.)",
    "Minor procedures and wound care",
    "Sports and DOT physicals",
    "Skin lesion and mole evaluation",
    "Joint injections",
    "Mental health screening and support",
    "Preventive care and health screenings",
    "Discounted labs and imaging",
    "Discounted prescription medications",
    "Telemedicine / virtual visits",
    "Pediatric care",
    "Women's health services",
    "Men's health services",
]


# ---------------------------------------------------------------------------
# Helper functions for building dynamic responses
# ---------------------------------------------------------------------------

def _fill_placeholders(text: str) -> str:
    """Replace {placeholder} tokens with values from PRACTICE_INFO."""
    for key, value in PRACTICE_INFO.items():
        text = text.replace(f"{{{key}}}", value)
    return text


def _locations_response() -> str:
    lines = ["Reliant DPC has the following locations:\n"]
    for loc in LOCATIONS:
        providers = (
            ", ".join(loc["providers"])
            if loc["providers"]
            else "Contact us for provider details"
        )
        lines.append(f"- {loc['name']}: {loc['address']}")
        lines.append(f"  Providers: {providers}")
    lines.append("\nCall {phone} or visit {website} for more details.")
    return "\n".join(lines)


def _providers_response() -> str:
    lines = ["Our providers across all locations include:\n"]
    for loc in LOCATIONS:
        for p in loc["providers"]:
            lines.append(f"- {p} ({loc['name']})")
    lines.append(
        "\nTo learn more about our team, visit {website}/our-team or "
        "call {phone}."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FAQ entries: (list of keyword regex patterns, response text)
# {placeholder} tokens are filled from PRACTICE_INFO at query time.
# ---------------------------------------------------------------------------

FAQ_ENTRIES = [
    # What is DPC?
    {
        "keywords": [
            r"\b(what|explain|tell me about)\b.*(dpc|direct primary care|membership model)",
            r"\bhow does (it|this|dpc|membership) work\b",
        ],
        "response": (
            "Direct Primary Care (DPC) is a membership-based healthcare model. "
            "Instead of billing through insurance for primary care, you pay a low "
            "monthly fee and get unlimited office visits, discounted medications "
            "and labs, and direct access to your doctor by phone, text, or email.\n\n"
            "There are no copays and no surprise bills for primary care services. "
            "Visit {website} or call us at {phone} to learn more."
        ),
    },
    # Membership / pricing
    {
        "keywords": [
            r"\b(cost|price|pricing|how much|fee|rate|afford|cheap|expensive)\b",
            r"\b(membership|sign.?up|join|enroll|register)\b",
        ],
        "response": (
            "Reliant DPC members pay a low monthly membership fee that covers "
            "unlimited office visits, discounted prescriptions, and direct access "
            "to your provider.\n\n"
            "For current membership pricing and to sign up, please visit "
            "{sign_up_url} or call us at {phone}. We also offer corporate "
            "memberships for businesses."
        ),
    },
    # Benefits
    {
        "keywords": [
            r"\b(benefit|what.*(get|include|cover)|perk|advantage)\b",
        ],
        "response": (
            "As a Reliant DPC member, you receive:\n\n"
            + "\n".join(f"- {b}" for b in MEMBERSHIP_BENEFITS)
            + "\n\nVisit {website} for full details."
        ),
    },
    # Insurance
    {
        "keywords": [
            r"\binsurance\b",
            r"\b(accept|take|bill).*(insurance|medicaid|medicare)\b",
        ],
        "response": (
            "Reliant DPC is a direct primary care practice, which means we do "
            "not bill insurance for primary care visits. Instead, you pay a "
            "monthly membership fee that covers unlimited visits.\n\n"
            "We recommend keeping a catastrophic or major-medical insurance plan "
            "for hospitalizations, specialist referrals, and emergencies. Your DPC "
            "membership handles your day-to-day primary care needs at a fraction "
            "of the typical cost.\n\n"
            "Call us at {phone} if you have questions about how DPC works with "
            "your current coverage."
        ),
    },
    # Locations
    {
        "keywords": [
            r"\b(location|office|address|where|clinic|near)\b",
        ],
        "response": _locations_response(),
    },
    # Providers / doctors
    {
        "keywords": [
            r"\b(doctor|provider|physician|who|staff|team|dr\.|nurse|aprn|pa\b)",
        ],
        "response": _providers_response(),
    },
    # Hours / availability
    {
        "keywords": [
            r"\b(hour|open|close|available|schedule|when)\b",
        ],
        "response": (
            "One of the biggest benefits of Reliant DPC is that your doctor is "
            "accessible when you need them. You can call, text, or email your "
            "provider for urgent needs even outside regular office hours.\n\n"
            "For specific office hours at your location, please call us at {phone} "
            "or email {email}."
        ),
    },
    # Appointments
    {
        "keywords": [
            r"\b(appointment|book|schedule a|come in|walk.?in|same.?day)\b",
        ],
        "response": (
            "As a Reliant DPC member, you can typically get same-day or next-day "
            "appointments. You can also reach your provider directly by phone, "
            "text, or email to discuss whether an in-person visit is needed.\n\n"
            "To schedule, contact your provider directly or call {phone}."
        ),
    },
    # Contact
    {
        "keywords": [
            r"\b(contact|reach out|call us|phone number|email address)\b",
        ],
        "response": (
            "You can reach Reliant DPC at:\n\n"
            "Phone: {phone}\n"
            "Email: {email}\n"
            "Website: {website}\n\n"
            "As a member, you also have your doctor's direct cell phone number "
            "for convenient access."
        ),
    },
    # Services
    {
        "keywords": [
            r"\b(service|treat|offer|do you (do|handle|see)|what can)\b",
        ],
        "response": (
            "Reliant DPC provides comprehensive primary care services including:\n\n"
            + "\n".join(f"- {s}" for s in SERVICES)
            + "\n\nIf you have a specific concern, feel free to ask and we'll "
            "let you know how we can help, or call us at {phone}."
        ),
    },
    # Labs / prescriptions / medications
    {
        "keywords": [
            r"\b(lab|blood.?work|test result|prescription|medic|rx|refill|pharmacy)\b",
        ],
        "response": (
            "Reliant DPC members receive discounted lab work and prescription "
            "medications. We provide transparent, upfront pricing on all labs "
            "and diagnostics before services are rendered, so there are no "
            "surprise bills.\n\n"
            "For prescription refills or lab questions, contact your provider "
            "directly or call {phone}."
        ),
    },
    # Telemedicine / virtual
    {
        "keywords": [
            r"\b(tele(medicine|health)|virtual|video.*(visit|call)|remote|online.*(visit|care))\b",
        ],
        "response": (
            "Yes! Reliant DPC offers telemedicine and virtual visits. As a member, "
            "you can reach your provider by phone, text, or email for many concerns "
            "without needing to come into the office.\n\n"
            "Contact your provider directly to arrange a virtual visit."
        ),
    },
    # Greeting
    {
        "keywords": [
            r"^(hi|hello|hey|good (morning|afternoon|evening)|howdy)",
        ],
        "response": (
            "Hello! Welcome to Reliant Direct Primary Care. I'm here to help "
            "answer your questions about our practice, membership, services, "
            "and more.\n\n"
            "How can I assist you today?"
        ),
    },
    # Thanks
    {
        "keywords": [
            r"\b(thank|thanks|appreciate|thx)\b",
        ],
        "response": (
            "You're welcome! If you have any other questions, feel free to ask. "
            "We're always here to help.\n\n"
            "You can also reach us at {phone} or {email} any time."
        ),
    },
]

# Default response when no FAQ matches
DEFAULT_RESPONSE = (
    "Thank you for your message. I want to make sure you get the best help "
    "possible.\n\n"
    "For general questions about our practice, membership, or services, "
    "I'm happy to help. Here are some things I can assist with:\n\n"
    "- Membership information and how to sign up\n"
    "- Our locations and providers\n"
    "- Services we offer\n"
    "- How Direct Primary Care works\n"
    "- Appointment and contact information\n\n"
    "For medical questions or concerns, I'll connect you with a member of "
    "our care team who can assist you directly.\n\n"
    "Call us any time at {phone} or email {email}."
)


def find_response(message: str) -> str | None:
    """Search the FAQ knowledge base for a matching response.

    Returns the formatted response string if a match is found,
    or None if no FAQ entry matches.
    """
    message_lower = message.lower().strip()

    for entry in FAQ_ENTRIES:
        for pattern in entry["keywords"]:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return _fill_placeholders(entry["response"])

    return None


def get_default_response() -> str:
    """Return the default response when no FAQ matches."""
    return _fill_placeholders(DEFAULT_RESPONSE)
