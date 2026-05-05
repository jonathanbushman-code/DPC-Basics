"""Aggregation logic for the SPRUS weekly call/SMS dashboard.

Normalizes raw Spruce call and message records and rolls them up by:
- phone ID (one row per phone -> one employee)
- provider (the provider attached to the patient on the other end)
- hour-of-day (for the working-hours volume chart)
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

import pytz

from services.business_hours import (
    business_hour_slots,
    is_business_hours,
    is_open_in_hour,
)

logger = logging.getLogger(__name__)


# ---------- field extraction helpers ----------

def _parse_dt(value, tz: pytz.BaseTzInfo) -> Optional[datetime]:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=pytz.UTC)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
        return dt.astimezone(tz)
    except (ValueError, TypeError):
        return None


def _phone_id(record: dict) -> str:
    """Extract the practice-side phone ID from a call/message record."""
    for key in (
        "organization_phone_id",
        "org_phone_id",
        "phone_number_id",
        "endpoint_id",
        "line_id",
    ):
        value = record.get(key)
        if value:
            return str(value)
    phone = record.get("organization_phone") or record.get("our_phone") or {}
    if isinstance(phone, dict):
        return str(phone.get("id") or phone.get("phone_number") or "unknown")
    return "unknown"


def _direction(record: dict) -> str:
    direction = record.get("direction")
    if direction:
        return str(direction).lower()
    if "inbound" in record:
        return "incoming" if record["inbound"] else "outgoing"
    return "unknown"


def _is_missed_call(record: dict) -> bool:
    if _direction(record) != "incoming":
        return False
    status = str(record.get("status") or record.get("outcome") or "").lower()
    if status in ("missed", "no_answer", "no-answer", "abandoned"):
        return True
    if record.get("missed") is True:
        return True
    if record.get("answered") is False:
        return True
    if record.get("duration_seconds") in (0, None) and not record.get("answered_at"):
        # No answer recorded and zero talk time
        return status not in ("voicemail",) and _direction(record) == "incoming"
    return False


def _duration_seconds(record: dict) -> int:
    for key in ("duration_seconds", "duration", "talk_time_seconds"):
        value = record.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return 0


def _patient_id(record: dict) -> Optional[str]:
    for key in ("patient_id", "contact_id", "endpoint_patient_id"):
        value = record.get(key)
        if value:
            return str(value)
    contact = record.get("contact") or record.get("patient") or {}
    if isinstance(contact, dict):
        pid = contact.get("id") or contact.get("patient_id")
        if pid:
            return str(pid)
    return None


def _message_type(record: dict) -> str:
    """Best guess at whether a message is SMS vs other (secure, email, etc.)."""
    for key in ("type", "channel", "kind", "medium"):
        value = record.get(key)
        if value:
            return str(value).lower()
    return "sms"


# ---------- aggregation ----------

class WeeklyAggregator:
    def __init__(
        self,
        timezone: str,
        provider_lookup=None,
        phone_mapping: Optional[dict] = None,
    ):
        self.tz = pytz.timezone(timezone)
        # provider_lookup: callable patient_id -> provider name (optional)
        self.provider_lookup = provider_lookup
        self.phone_mapping = phone_mapping or {}

    def aggregate(
        self,
        calls: list[dict],
        messages: list[dict],
        week_start: datetime,
        week_end: datetime,
    ) -> dict:
        per_phone = defaultdict(_empty_phone_bucket)
        provider_breakdown = defaultdict(_empty_provider_bucket)
        hourly = {h: {"total": 0, "missed": 0} for h in business_hour_slots()}

        for call in calls:
            started = _parse_dt(
                call.get("started_at") or call.get("start_time") or call.get("created_at"),
                self.tz,
            )
            if not started:
                continue
            phone_id = _phone_id(call)
            direction = _direction(call)
            duration = _duration_seconds(call)
            in_hours = is_business_hours(started)
            missed = _is_missed_call(call) and in_hours

            bucket = per_phone[phone_id]
            if direction == "incoming":
                bucket["incoming_calls"] += 1
            elif direction == "outgoing":
                bucket["outgoing_calls"] += 1
            bucket["total_call_seconds"] += duration
            if missed:
                bucket["missed_calls"] += 1

            patient_id = _patient_id(call)
            provider_name = self._resolve_provider(patient_id)
            pb = provider_breakdown[provider_name]
            if direction == "incoming":
                pb["incoming_calls"] += 1
            elif direction == "outgoing":
                pb["outgoing_calls"] += 1
            if missed:
                pb["missed_calls"] += 1

            # Hourly volume during business hours only
            if in_hours and started.hour in hourly:
                hourly[started.hour]["total"] += 1
                if missed:
                    hourly[started.hour]["missed"] += 1

        for msg in messages:
            sent = _parse_dt(
                msg.get("sent_at") or msg.get("created_at") or msg.get("timestamp"),
                self.tz,
            )
            if not sent:
                continue
            if _message_type(msg) not in ("sms", "text", "phone"):
                # only count SMS; secure messages and others excluded
                continue

            phone_id = _phone_id(msg)
            direction = _direction(msg)
            bucket = per_phone[phone_id]
            if direction == "incoming":
                bucket["incoming_sms"] += 1
            elif direction == "outgoing":
                bucket["outgoing_sms"] += 1

            patient_id = _patient_id(msg)
            provider_name = self._resolve_provider(patient_id)
            pb = provider_breakdown[provider_name]
            if direction == "incoming":
                pb["incoming_sms"] += 1
            elif direction == "outgoing":
                pb["outgoing_sms"] += 1

        # Decorate per-phone rows with mapping metadata + readable totals
        per_phone_rows = []
        for phone_id, bucket in per_phone.items():
            mapping = self.phone_mapping.get(phone_id, {})
            per_phone_rows.append({
                "phone_id": phone_id,
                "label": mapping.get("name") or phone_id,
                "employee": mapping.get("employee") or "",
                "missed_calls": bucket["missed_calls"],
                "incoming_calls": bucket["incoming_calls"],
                "outgoing_calls": bucket["outgoing_calls"],
                "total_call_seconds": bucket["total_call_seconds"],
                "total_call_minutes": round(bucket["total_call_seconds"] / 60, 1),
                "incoming_sms": bucket["incoming_sms"],
                "outgoing_sms": bucket["outgoing_sms"],
            })
        per_phone_rows.sort(
            key=lambda r: (-r["missed_calls"], -r["total_call_seconds"], r["label"])
        )

        provider_rows = []
        for provider, bucket in provider_breakdown.items():
            provider_rows.append({
                "provider": provider,
                **bucket,
                "total_calls": bucket["incoming_calls"] + bucket["outgoing_calls"],
                "total_sms": bucket["incoming_sms"] + bucket["outgoing_sms"],
            })
        provider_rows.sort(key=lambda r: -r["total_calls"])

        # Hourly volume (chart-ready)
        hourly_rows = []
        for hour in business_hour_slots():
            hourly_rows.append({
                "hour": hour,
                "total": hourly[hour]["total"],
                "missed": hourly[hour]["missed"],
            })

        totals = {
            "missed_calls": sum(r["missed_calls"] for r in per_phone_rows),
            "incoming_calls": sum(r["incoming_calls"] for r in per_phone_rows),
            "outgoing_calls": sum(r["outgoing_calls"] for r in per_phone_rows),
            "total_call_minutes": round(
                sum(r["total_call_seconds"] for r in per_phone_rows) / 60, 1
            ),
            "incoming_sms": sum(r["incoming_sms"] for r in per_phone_rows),
            "outgoing_sms": sum(r["outgoing_sms"] for r in per_phone_rows),
        }

        return {
            "week_start": week_start,
            "week_end": week_end,
            "per_phone": per_phone_rows,
            "by_provider": provider_rows,
            "hourly": hourly_rows,
            "totals": totals,
        }

    def _resolve_provider(self, patient_id: Optional[str]) -> str:
        if not patient_id or not self.provider_lookup:
            return "Unassigned / Unknown"
        try:
            name = self.provider_lookup(patient_id)
        except Exception:
            logger.exception("Provider lookup failed for patient %s", patient_id)
            return "Unassigned / Unknown"
        return name or "Unassigned / Unknown"


def _empty_phone_bucket() -> dict:
    return {
        "missed_calls": 0,
        "incoming_calls": 0,
        "outgoing_calls": 0,
        "total_call_seconds": 0,
        "incoming_sms": 0,
        "outgoing_sms": 0,
    }


def _empty_provider_bucket() -> dict:
    return {
        "incoming_calls": 0,
        "outgoing_calls": 0,
        "missed_calls": 0,
        "incoming_sms": 0,
        "outgoing_sms": 0,
    }
