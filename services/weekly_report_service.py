"""Service for generating a weekly Spruce phone & messaging activity report.

The report covers the previous Monday-through-Sunday period and includes:

1. Per-endpoint (physical phone) summary of inbound/outbound calls,
   total call minutes, and inbound/outbound SMS counts.
2. Hourly volume chart data (calls + SMS combined) for a bar-graph
   visualisation in the HTML template.
3. Missed-call count during defined business hours:
   Mon-Thu 8 AM - 5 PM CST (lunch break 12-1 PM excluded)
   Friday  8 AM - 12 PM CST

Spruce models all communication as Conversations containing ConversationItems.
Calls and SMS each create their own conversation per contact+channel.  We list
conversations created during the target week, then classify each item as a call
or SMS based on its ``eventType`` field.
"""

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
from jinja2 import Environment, FileSystemLoader

from clients.spruce_client import SpruceClient
from config import BusinessHoursConfig, SUMMARY_OUTPUT_DIR

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

# Spruce eventType values that represent phone calls
_CALL_EVENT_TYPES = {"inboundCall", "outboundCall", "inbound_call", "outbound_call"}
# Spruce eventType values that represent SMS / text messages
_SMS_EVENT_TYPES = {"inboundSMS", "outboundSMS", "inbound_sms", "outbound_sms",
                    "inboundMessage", "outboundMessage", "sms"}


class WeeklyReportService:
    """Fetches Spruce conversation data and generates a weekly activity report."""

    def __init__(self, spruce_client: SpruceClient = None):
        self.spruce = spruce_client or SpruceClient()
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        self.biz_tz = pytz.timezone(BusinessHoursConfig.TIMEZONE)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate_weekly_report(self, week_start: datetime = None) -> str:
        """Generate the full weekly report and return the output file path.

        Args:
            week_start: The Monday 00:00 UTC of the target week.  Defaults to
                        the most-recently completed Monday-Sunday week.

        Returns:
            Path to the generated PDF (or HTML fallback) file.
        """
        if week_start is None:
            week_start = _previous_week_start()

        week_end = week_start + timedelta(days=7)
        start_iso = week_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = week_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("Generating weekly report for %s -> %s", start_iso, end_iso)

        # 1. Fetch internal endpoints (phone lines / physical phones)
        endpoints = self.spruce.get_internal_endpoints()
        endpoint_map = self._build_endpoint_map(endpoints)

        # 2. Fetch conversations created during the target week
        conversations = self.spruce.get_conversations(start_from=start_iso)

        # 3. Classify conversation items into calls and SMS records
        calls, sms_messages = self._classify_conversations(
            conversations, week_start, week_end
        )
        logger.info(
            "Classified %d call records and %d SMS records",
            len(calls), len(sms_messages),
        )

        # 4. Compute report sections
        per_line_stats = self._per_line_stats(calls, sms_messages, endpoint_map)
        hourly_volume = self._hourly_volume(calls, sms_messages)
        missed_during_biz = self._missed_calls_during_business_hours(
            calls, endpoint_map
        )

        # 5. Render HTML
        template = self.jinja_env.get_template("weekly_report.html")
        html_content = template.render(
            week_start_date=week_start.strftime("%B %d, %Y"),
            week_end_date=(week_end - timedelta(days=1)).strftime("%B %d, %Y"),
            per_line_stats=per_line_stats,
            hourly_volume=hourly_volume,
            max_hourly_volume=max(
                (h["total"] for h in hourly_volume), default=1
            ),
            missed_during_biz=missed_during_biz,
            total_missed=sum(m["missed_count"] for m in missed_during_biz),
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

        # 6. Write output
        os.makedirs(SUMMARY_OUTPUT_DIR, exist_ok=True)
        date_str = week_start.strftime("%Y-%m-%d")
        return self._write_output(html_content, date_str)

    # ------------------------------------------------------------------
    # Conversation classification
    # ------------------------------------------------------------------

    @staticmethod
    def _build_endpoint_map(endpoints: list[dict]) -> dict[str, str]:
        """Map internal-endpoint IDs to display names.

        Each endpoint represents a Spruce phone number, fax, email, or
        Spruce Link.  The ID is what appears on conversation items and maps
        back to a physical phone at a desk.
        """
        emap: dict[str, str] = {}
        for ep in endpoints:
            eid = ep.get("id", "")
            label = (
                ep.get("label")
                or ep.get("name")
                or ep.get("address")
                or ep.get("number")
                or eid
                or "Unknown"
            )
            emap[eid] = label
        return emap

    def _classify_conversations(
        self,
        conversations: list[dict],
        week_start: datetime,
        week_end: datetime,
    ) -> tuple[list[dict], list[dict]]:
        """Walk conversations and extract normalised call / SMS records.

        Each conversation may carry embedded ``items`` or ``lastItem``.
        We normalise these into flat dicts that downstream processing can
        consume uniformly.

        Returns:
            (calls, sms_messages) — two lists of normalised record dicts.
        """
        calls: list[dict] = []
        sms_messages: list[dict] = []

        for conv in conversations:
            # Determine the internal endpoint (phone line) for this conversation
            endpoint_id = (
                conv.get("internalEndpointId")
                or conv.get("internalendpointId")
                or conv.get("endpointId")
                or conv.get("endpoint_id")
                or "unknown"
            )

            # Conversations may embed items directly or just carry summary data
            items = conv.get("items") or conv.get("conversationItems") or []

            # If no embedded items, treat the conversation itself as one event
            if not items:
                items = [conv]

            for item in items:
                record = self._normalise_item(item, endpoint_id, week_start, week_end)
                if record is None:
                    continue

                if record["record_type"] == "call":
                    calls.append(record)
                elif record["record_type"] == "sms":
                    sms_messages.append(record)

        return calls, sms_messages

    def _normalise_item(
        self,
        item: dict,
        fallback_endpoint_id: str,
        week_start: datetime,
        week_end: datetime,
    ) -> dict | None:
        """Convert a raw Spruce conversation item into a normalised record.

        Returns None if the item falls outside the target week or has an
        unrecognised type.
        """
        event_type = (
            item.get("eventType")
            or item.get("event_type")
            or item.get("type")
            or ""
        )

        # Determine timestamp
        ts_raw = (
            item.get("createdAt")
            or item.get("created_at")
            or item.get("startedAt")
            or item.get("started_at")
            or item.get("timestamp")
            or ""
        )
        dt = self._parse_timestamp(ts_raw)
        if dt is not None:
            if dt < week_start.replace(tzinfo=pytz.utc) or dt >= week_end.replace(tzinfo=pytz.utc):
                return None

        endpoint_id = (
            item.get("internalEndpointId")
            or item.get("endpointId")
            or item.get("endpoint_id")
            or fallback_endpoint_id
        )

        # Call event data may be nested under "event" or "data"
        event_data = item.get("event", {}).get("data", {}) or item.get("data", {})

        # Classify
        if event_type in _CALL_EVENT_TYPES or "call" in event_type.lower():
            direction = "inbound" if "inbound" in event_type.lower() else "outbound"
            answered = event_data.get("answered", True)
            duration = event_data.get("duration") or item.get("duration") or 0
            failed = event_data.get("failed", False)

            # A call is "missed" if it was inbound, not answered, and not failed
            missed = direction == "inbound" and not answered and not failed

            return {
                "record_type": "call",
                "direction": direction,
                "endpoint_id": endpoint_id,
                "timestamp": ts_raw,
                "duration": duration,
                "answered": answered,
                "missed": missed,
                "from_number": (
                    item.get("from")
                    or item.get("caller")
                    or item.get("externalAddress")
                    or item.get("external_address")
                    or "Unknown"
                ),
            }

        if event_type in _SMS_EVENT_TYPES or "sms" in event_type.lower() or "message" in event_type.lower():
            direction = "inbound" if "inbound" in event_type.lower() else "outbound"
            return {
                "record_type": "sms",
                "direction": direction,
                "endpoint_id": endpoint_id,
                "timestamp": ts_raw,
            }

        return None

    # ------------------------------------------------------------------
    # Section 1: Per-line call & SMS stats
    # ------------------------------------------------------------------

    def _per_line_stats(
        self,
        calls: list[dict],
        sms_messages: list[dict],
        endpoint_map: dict,
    ) -> list[dict]:
        """Aggregate call and SMS counts per internal endpoint (physical phone).

        Returns a sorted list (highest activity first) of dicts containing:
            line_id, line_name,
            inbound_calls, outbound_calls, total_call_minutes,
            inbound_sms, outbound_sms, total_activity
        """
        stats: dict[str, dict] = defaultdict(lambda: {
            "inbound_calls": 0,
            "outbound_calls": 0,
            "total_call_seconds": 0,
            "inbound_sms": 0,
            "outbound_sms": 0,
        })

        for call in calls:
            lid = call.get("endpoint_id", "unknown")
            if call["direction"] == "inbound":
                stats[lid]["inbound_calls"] += 1
            else:
                stats[lid]["outbound_calls"] += 1
            stats[lid]["total_call_seconds"] += call.get("duration", 0)

        for msg in sms_messages:
            lid = msg.get("endpoint_id", "unknown")
            if msg["direction"] == "inbound":
                stats[lid]["inbound_sms"] += 1
            else:
                stats[lid]["outbound_sms"] += 1

        result = []
        for lid, s in stats.items():
            total_minutes = round(s["total_call_seconds"] / 60, 1)
            result.append({
                "line_id": lid,
                "line_name": endpoint_map.get(lid, lid),
                "inbound_calls": s["inbound_calls"],
                "outbound_calls": s["outbound_calls"],
                "total_call_minutes": total_minutes,
                "inbound_sms": s["inbound_sms"],
                "outbound_sms": s["outbound_sms"],
                "total_activity": (
                    s["inbound_calls"] + s["outbound_calls"]
                    + s["inbound_sms"] + s["outbound_sms"]
                ),
            })

        result.sort(key=lambda r: r["total_activity"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Section 2: Hourly volume distribution (for bar chart)
    # ------------------------------------------------------------------

    def _hourly_volume(
        self, calls: list[dict], sms_messages: list[dict]
    ) -> list[dict]:
        """Count combined call + SMS events per hour of the day (0-23).

        Hours are in Central time.  Returns a list of 24 dicts:
        {hour, hour_label, calls, sms, total}.
        """
        buckets: dict[int, dict] = {
            h: {"calls": 0, "sms": 0} for h in range(24)
        }

        for call in calls:
            hour = self._extract_local_hour(call.get("timestamp", ""))
            if hour is not None:
                buckets[hour]["calls"] += 1

        for msg in sms_messages:
            hour = self._extract_local_hour(msg.get("timestamp", ""))
            if hour is not None:
                buckets[hour]["sms"] += 1

        result = []
        for h in range(24):
            b = buckets[h]
            result.append({
                "hour": h,
                "hour_label": _format_hour(h),
                "calls": b["calls"],
                "sms": b["sms"],
                "total": b["calls"] + b["sms"],
            })
        return result

    # ------------------------------------------------------------------
    # Section 3: Missed calls during business hours
    # ------------------------------------------------------------------

    def _missed_calls_during_business_hours(
        self, calls: list[dict], endpoint_map: dict
    ) -> list[dict]:
        """Count missed calls that occurred during defined business hours.

        Business hours (Central Standard Time):
            Mon-Thu: 8:00 AM - 5:00 PM, excluding 12:00 - 1:00 PM lunch
            Friday:  8:00 AM - 12:00 PM

        Returns a list of dicts per endpoint:
            {line_id, line_name, missed_count, missed_details}
        where missed_details is a list of {timestamp, from_number, day_of_week}.
        """
        per_line: dict[str, list[dict]] = defaultdict(list)

        for call in calls:
            if not call.get("missed", False):
                continue

            dt = self._parse_timestamp(call.get("timestamp", ""))
            if dt is None:
                continue

            dt_central = dt.astimezone(self.biz_tz)
            if not self._is_business_hours(dt_central):
                continue

            lid = call.get("endpoint_id", "unknown")
            per_line[lid].append({
                "timestamp": dt_central.strftime("%a %m/%d %I:%M %p"),
                "from_number": call.get("from_number", "Unknown"),
                "day_of_week": dt_central.strftime("%A"),
            })

        result = []
        for lid, details in per_line.items():
            result.append({
                "line_id": lid,
                "line_name": endpoint_map.get(lid, lid),
                "missed_count": len(details),
                "missed_details": sorted(
                    details, key=lambda d: d["timestamp"]
                ),
            })
        result.sort(key=lambda r: r["missed_count"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_business_hours(dt: datetime) -> bool:
        """Return True if *dt* (already in Central time) falls within office hours."""
        weekday = dt.weekday()  # Monday=0 .. Sunday=6
        hour = dt.hour

        if weekday > 4:  # Saturday or Sunday
            return False

        if weekday == 4:  # Friday
            return BusinessHoursConfig.FRIDAY_START <= hour < BusinessHoursConfig.FRIDAY_END

        # Monday - Thursday
        if hour < BusinessHoursConfig.MON_THU_START or hour >= BusinessHoursConfig.MON_THU_END:
            return False
        # Exclude lunch break
        if BusinessHoursConfig.LUNCH_START <= hour < BusinessHoursConfig.LUNCH_END:
            return False
        return True

    def _extract_local_hour(self, iso_str: str) -> int | None:
        """Parse an ISO timestamp and return the hour in Central time."""
        dt = self._parse_timestamp(iso_str)
        if dt is None:
            return None
        return dt.astimezone(self.biz_tz).hour

    @staticmethod
    def _parse_timestamp(iso_str: str) -> datetime | None:
        """Best-effort ISO-8601 timestamp parser."""
        if not iso_str:
            return None
        try:
            cleaned = iso_str.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            logger.debug("Could not parse timestamp: %s", iso_str)
            return None

    @staticmethod
    def _write_output(html_content: str, date_str: str) -> str:
        """Write to PDF (preferred) or fall back to HTML."""
        pdf_path = os.path.join(
            SUMMARY_OUTPUT_DIR, f"weekly_report_{date_str}.pdf"
        )
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(pdf_path)
            logger.info("Weekly report PDF generated: %s", pdf_path)
            return pdf_path
        except ImportError:
            logger.warning(
                "weasyprint not available, falling back to HTML output"
            )
            html_path = os.path.join(
                SUMMARY_OUTPUT_DIR, f"weekly_report_{date_str}.html"
            )
            with open(html_path, "w") as f:
                f.write(html_content)
            logger.info("Weekly report HTML generated: %s", html_path)
            return html_path


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _previous_week_start() -> datetime:
    """Return the Monday 00:00 UTC of the most recently completed week."""
    today = datetime.utcnow().date()
    days_since_monday = today.weekday()
    # If today is Monday, we want the week that just ended (7 days back)
    if days_since_monday == 0:
        monday = today - timedelta(days=7)
    else:
        monday = today - timedelta(days=days_since_monday)
    return datetime(monday.year, monday.month, monday.day, tzinfo=pytz.utc)


def _format_hour(h: int) -> str:
    """Format 0-23 hour into a readable label like '8 AM' or '2 PM'."""
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"
