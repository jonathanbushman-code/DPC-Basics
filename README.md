# DPC-Basics: Clinical Analytics Summary Agent

Automated agent that pulls daily appointments from **Elation Health** and delivers a clinical analytics summary to a **Spruce Health** user.

## How It Works

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
| `TIMEZONE` | Practice timezone (e.g., `America/New_York`) |

### 3. Run

**Scheduled mode** (runs continuously, executes at configured times):
```bash
python main.py
```

**Single execution** (run both steps immediately):
```bash
python main.py --run-once
```

## API References

- [Elation Health API Docs](https://docs.elationhealth.com/reference/introduction)
- [Spruce Health API Docs](https://developer.sprucehealth.com/docs/overview)

## Project Structure

```
├── main.py                      # Entry point with APScheduler
├── config.py                    # Environment-based configuration
├── clients/
│   ├── elation_client.py        # Elation OAuth + REST API client
│   └── spruce_client.py         # Spruce messaging + media upload client
├── services/
│   ├── appointment_service.py   # Appointment fetching and organization
│   ├── analytics_service.py     # PDF/HTML summary generation
│   └── notification_service.py  # Spruce delivery orchestration
└── templates/
    └── clinical_summary.html    # Jinja2 report template
```
