# DPC-Basics: Clinical Analytics & Patient Chatbot

Automated tools for **Reliant Direct Primary Care** built on the **Spruce Health** and **Elation Health** APIs:

1. **Daily Analytics Agent** — Pulls appointments from Elation and delivers a clinical summary to Spruce.
2. **Patient Chatbot** — A Spruce-integrated virtual assistant that answers patient questions from a knowledge base and escalates medical concerns to providers.

---

## Daily Analytics Agent

### How It Works

| Time | Action |
|------|--------|
| **12:01 AM** | Fetches all appointments for today from Elation Health (entire practice) |
| 12:01 AM | Enriches appointments with patient and provider details |
| 12:01 AM | Generates a Clinical Analytics Summary PDF |
| **7:00 AM** | Sends the summary document to a configured Spruce Health conversation |

## Summary Report Contents

- **Key Metrics**: Total appointments, unique patients, provider count, clinical hours, average duration
- **Status Breakdown**: Appointments by status (Scheduled, Confirmed, Checked In, etc.)
- **Time Block View**: Appointments grouped by morning/midday/afternoon/evening
- **Provider Breakdown**: Per-provider appointment schedules

---

## Patient Chatbot

### How It Works

The chatbot receives incoming patient messages via Spruce webhooks and processes them through a two-stage pipeline:

| Step | Description |
|------|-------------|
| **1. Triage** | Every message is scanned for medical urgency (emergency, urgent, moderate, or low) |
| **2a. Emergency** | Life-threatening keywords (chest pain, stroke, etc.) trigger a **call-911** response and immediate provider escalation |
| **2b. Urgent/Moderate** | Medical symptoms trigger an acknowledgment and **provider escalation** via internal Spruce notes |
| **2c. Low (General)** | Non-medical questions are answered from the **knowledge base** (membership, locations, services, etc.) |

### Triage Levels

| Level | Action | Examples |
|-------|--------|----------|
| **EMERGENCY** | Auto-respond with 911 guidance + escalate to provider | Chest pain, stroke symptoms, suicidal ideation, severe bleeding |
| **URGENT** | Auto-respond + escalate to provider | High fever, severe pain, fractures, head injury |
| **MODERATE** | Auto-respond + escalate to provider | Cough, rash, headache, stomach issues, medication questions |
| **LOW** | Answer from knowledge base | Membership questions, locations, services, appointments |

### Knowledge Base

The chatbot's knowledge base covers:
- Practice information (Reliant DPC)
- Membership details and benefits
- Locations (Enid, Fairview, Altus, Cherokee, OK)
- Providers at each location
- Services offered
- Insurance / DPC model explanation
- Contact information
- Appointment scheduling

### Running the Chatbot

**Start the webhook server:**
```bash
python chatbot_server.py
```

**Register the webhook with Spruce (one-time setup):**
```bash
python chatbot_server.py --register-webhook
```

**List registered webhooks:**
```bash
python chatbot_server.py --list-webhooks
```

---

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Required values:**

| Variable | Description |
|----------|-------------|
| `ELATION_CLIENT_ID` | OAuth client ID from Elation developer portal |
| `ELATION_CLIENT_SECRET` | OAuth client secret |
| `ELATION_API_BASE_URL` | `https://sandbox.elationemr.com/api/2.0` (sandbox) or `https://app.elationemr.com/api/2.0` (production) |
| `SPRUCE_API_TOKEN` | Bearer token from Spruce Settings > Integrations & API |
| `SPRUCE_CONVERSATION_ID` | The Spruce conversation ID to send the summary to |
| `SPRUCE_WEBHOOK_SECRET` | Webhook signing secret (provided during registration) |
| `TIMEZONE` | Practice timezone (e.g., `America/New_York`) |
| `CHATBOT_PUBLIC_URL` | Public URL where the chatbot server is accessible |
| `SPRUCE_ESCALATION_CONVERSATION_ID` | Team conversation for escalation alerts |

### 3. Run

**Daily Analytics Agent** (scheduled mode):
```bash
python main.py
```

**Daily Analytics Agent** (single execution):
```bash
python main.py --run-once
```

**Patient Chatbot:**
```bash
python chatbot_server.py
```

## API References

- [Elation Health API Docs](https://docs.elationhealth.com/reference/introduction)
- [Spruce Health API Docs](https://developer.sprucehealth.com/docs/overview)

## Project Structure

```
├── main.py                      # Daily analytics agent entry point
├── chatbot_server.py            # Chatbot webhook server entry point
├── config.py                    # Environment-based configuration
├── clients/
│   ├── elation_client.py        # Elation OAuth + REST API client
│   └── spruce_client.py         # Spruce messaging, media, and webhook client
├── chatbot/
│   ├── knowledge_base.py        # Practice FAQ and keyword-matching responses
│   ├── triage_engine.py         # Medical urgency classification and escalation
│   ├── message_handler.py       # Message processing pipeline
│   └── webhook_server.py        # Flask server for Spruce webhook events
├── services/
│   ├── appointment_service.py   # Appointment fetching and organization
│   ├── analytics_service.py     # PDF/HTML summary generation
│   └── notification_service.py  # Spruce delivery orchestration
└── templates/
    └── clinical_summary.html    # Jinja2 report template
```
