# DPC-Basics: Clinical Analytics & SPRUS Weekly Report Agents

Automated agents that:

1. Pull daily appointments from **Elation Health** and deliver a clinical analytics summary to a **Spruce Health** conversation.
2. Pull a week of **SPRUS** (Spruce) call and SMS activity and deliver a per-phone / per-provider dashboard with an hourly call-volume chart.

## How It Works

### Daily Clinical Analytics

| Time | Action |
|------|--------|
| **12:01 AM** | Fetches all appointments for today from Elation Health (entire practice) |
| 12:01 AM | Enriches appointments with patient and provider details |
| 12:01 AM | Generates a Clinical Analytics Summary PDF |
| **7:00 AM** | Sends the summary document to a configured Spruce Health conversation |

### Weekly SPRUS Report

| Time | Action |
|------|--------|
| **Monday 7:00 AM** (configurable) | Pulls calls + SMS from the last 7 days from Spruce |
| | Aggregates per phone ID, per provider, and per hour-of-day |
| | Renders a PDF with the dashboard tables and an hourly volume chart |
| | Delivers the PDF to a configured Spruce conversation |

The weekly report includes:

- **Totals** — missed calls during business hours, incoming/outgoing call counts, total talk-time minutes, incoming/outgoing SMS counts.
- **Per-phone breakdown** — one row per phone ID (mapped to an employee via `phone_mapping.json`).
- **Per-provider breakdown** — calls/SMS rolled up by the patient's assigned provider in Elation.
- **Hourly call-volume chart** — stacked bar showing answered vs missed calls for each hour of the working day.

#### Business Hours

- Monday – Thursday: **08:00 – 12:00** and **13:00 – 17:00**
- Friday: **08:00 – 12:00** only (afternoons closed)
- Lunch break **12:00 – 13:00** is excluded
- Saturday and Sunday are excluded
- A "missed call" only counts if it occurred during business hours

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
| `SPRUCE_CONVERSATION_ID` | The Spruce conversation ID to send the daily summary to |
| `TIMEZONE` | Practice timezone (e.g., `America/New_York`) |

**Weekly report values:**

| Variable | Description | Default |
|----------|-------------|---------|
| `WEEKLY_REPORT_DAY` | Cron day-of-week (`mon`, `tue`, ...) | `mon` |
| `WEEKLY_REPORT_HOUR` | Hour to deliver weekly report | `7` |
| `WEEKLY_REPORT_MINUTE` | Minute to deliver weekly report | `0` |
| `WEEKLY_REPORT_CONVERSATION_ID` | Conversation to deliver to (falls back to `SPRUCE_CONVERSATION_ID`) | (fallback) |
| `PHONE_MAPPING_FILE` | Optional JSON mapping phone IDs to employees | `phone_mapping.json` |
| `WEEKLY_REPORT_ENRICH_PROVIDERS` | Look up patient → provider in Elation for the breakdown | `true` |
| `SPRUCE_CALLS_ENDPOINT` | Override for the Spruce calls endpoint | `<base>/v1/calls` |
| `SPRUCE_MESSAGES_ENDPOINT` | Override for the Spruce messages endpoint | `<base>/v1/messages` |

### 3. Map Phone IDs to Employees (Optional)

Copy `phone_mapping.example.json` to `phone_mapping.json` and fill in your phone IDs:

```json
{
  "PHN_abc123": { "name": "Front Desk", "employee": "Jane Doe" }
}
```

Phone IDs without a mapping still appear in the report — the raw ID is shown.

### 4. Run

**Scheduled mode** (runs continuously, executes daily and weekly jobs):
```bash
python main.py
```

**Single execution of the daily flow** (for testing):
```bash
python main.py --run-once
```

**Single execution of the weekly report** (renders + delivers):
```bash
python main.py --weekly-once
```

**Render the weekly report without sending** (writes file to `output/`):
```bash
python main.py --weekly-dry-run
```

## API References

- [Elation Health API Docs](https://docs.elationhealth.com/reference/introduction)
- [Spruce Health API Docs](https://developer.sprucehealth.com/docs/overview)

## Project Structure

```
├── main.py                              # Entry point with APScheduler (daily + weekly)
├── config.py                            # Environment-based configuration
├── clients/
│   ├── elation_client.py                # Elation OAuth + REST API client
│   ├── spruce_client.py                 # Spruce messaging + media upload client
│   └── spruce_reporting_client.py       # Spruce calls/messages reporting client
├── services/
│   ├── appointment_service.py           # Appointment fetching and organization
│   ├── analytics_service.py             # Daily PDF/HTML summary generation
│   ├── notification_service.py          # Spruce delivery orchestration (daily)
│   ├── business_hours.py                # Mon–Fri business-hours helpers
│   ├── weekly_aggregation.py            # Per-phone / per-provider / hourly aggregator
│   ├── chart_service.py                 # matplotlib hourly-volume chart
│   └── weekly_report_service.py         # Weekly report orchestration + delivery
├── templates/
│   ├── clinical_summary.html            # Daily summary template
│   └── weekly_report.html               # Weekly SPRUS report template
└── phone_mapping.example.json           # Example phone-ID -> employee map
```
