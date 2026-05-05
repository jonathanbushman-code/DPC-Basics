"""Render the hourly call-volume bar chart for the weekly report."""

import base64
import io
import logging

from services.business_hours import hour_label

logger = logging.getLogger(__name__)


def render_hourly_volume_chart_png(hourly_rows: list[dict]) -> bytes:
    """Stacked bar chart: total calls per hour with missed-call portion.

    Returns PNG bytes. Uses matplotlib with the Agg backend so this is
    safe to run in a headless scheduler process.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hours = [r["hour"] for r in hourly_rows]
    totals = [r["total"] for r in hourly_rows]
    missed = [r["missed"] for r in hourly_rows]
    answered = [t - m for t, m in zip(totals, missed)]
    labels = [hour_label(h) for h in hours]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(labels, answered, label="Answered / outgoing", color="#0056b3")
    ax.bar(labels, missed, bottom=answered, label="Missed", color="#c0392b")

    ax.set_title("Call Volume by Hour (Business Hours)")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Calls")
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    for i, total in enumerate(totals):
        if total:
            ax.text(i, total + 0.2, str(total), ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def png_to_data_uri(png_bytes: bytes) -> str:
    """Encode PNG bytes as an inline data URI for HTML/PDF embedding."""
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"
