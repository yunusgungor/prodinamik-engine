"""
Prodinamik Engine v1.1 — Alert Manager

Webhook-based alert integration for Slack, Telegram, and generic channels.
Designed for both Prometheus Alertmanager and direct engine integration.

Usage:
    # Direct engine alert
    alert = AlertManager(slack_webhook="https://hooks.slack.com/...")
    alert.send_alert("warning", "Budget near limit", metrics={"usage": 0.85})

    # Via Alertmanager webhook receiver
    flask endpoint POST /alertmanager
        data = request.json
        alert = AlertManager()
        alert.handle_alertmanager_webhook(data)

    # CLI
    prodinamik alert send --level warning "Budget at 85%"
    prodinamik alert test --channel slack
"""

import json
import os
import time
import hashlib
import threading
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Optional, Callable


# ──────────────────────────────────────────────
# Alert Types
# ──────────────────────────────────────────────

ALERT_SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class Alert:
    """Single alert event"""

    def __init__(self, level: str, title: str, message: str = "",
                 metrics: dict = None, source: str = "engine"):
        assert level in ("critical", "warning", "info"), f"Invalid level: {level}"
        self.level = level
        self.title = title
        self.message = message
        self.metrics = metrics or {}
        self.source = source
        self.timestamp = datetime.now().isoformat()
        self.id = hashlib.md5(f"{self.timestamp}:{title}".encode()).hexdigest()[:12]

    @property
    def emoji(self) -> str:
        return ALERT_SEVERITY_EMOJI.get(self.level, "⚪")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "metrics": self.metrics,
            "source": self.source,
            "timestamp": self.timestamp,
        }

    def to_slack_payload(self) -> dict:
        color = {"critical": "danger", "warning": "warning", "info": "good"}[self.level]
        fields = []
        for k, v in self.metrics.items():
            fields.append({
                "title": k.replace("_", " ").title(),
                "value": str(v),
                "short": True,
            })

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{self.emoji} {self.title}",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": self.message or f"*Level:* {self.level.upper()}\n*Source:* {self.source}\n*Time:* {self.timestamp}",
                }
            },
        ]
        if fields:
            blocks.append({
                "type": "section",
                "fields": fields,
            })
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"ID: `{self.id}` · Prodinamik Engine Alert"}
            ],
        })

        return {
            "text": f"{self.emoji} [{self.level.upper()}] {self.title}",
            "attachments": [{
                "color": color,
                "blocks": blocks,
            }],
        }

    def to_telegram_payload(self) -> str:
        metric_lines = "\n".join(
            f"  • <b>{k}</b>: <code>{v}</code>"
            for k, v in self.metrics.items()
        )
        parts = [
            f"{self.emoji} <b>[{self.level.upper()}] {self.title}</b>",
            "",
            self.message or "",
            "",
            f"<b>Source:</b> {self.source}",
            f"<b>Time:</b> {self.timestamp}",
        ]
        if metric_lines:
            parts.append("")
            parts.append("<b>Metrics:</b>")
            parts.append(metric_lines)
        parts.append("")
        parts.append(f"<code>ID: {self.id}</code>")

        return "\n".join(parts)

    def to_alertmanager_payload(self) -> dict:
        """Format for Prometheus Alertmanager webhook"""
        return {
            "labels": {
                "alertname": self.title,
                "severity": self.level,
                "source": self.source,
            },
            "annotations": {
                "summary": self.title,
                "description": self.message,
            },
            "startsAt": self.timestamp,
            "generatorURL": "",
        }


# ──────────────────────────────────────────────
# Alert Manager
# ──────────────────────────────────────────────

class AlertManager:
    """
    Central alert manager with webhook delivery.

    Supports:
    - Slack webhook (Incoming Webhooks API)
    - Telegram bot (sendMessage API)
    - Generic webhook (custom URL)
    - Rate-limited delivery (min_interval_sec)
    - Deduplication (same alert suppressed for window_sec)
    """

    def __init__(self, slack_webhook: str = "", telegram_token: str = "",
                 telegram_chat_id: str = "", generic_webhook: str = "",
                 min_interval_sec: int = 60, dedup_window_sec: int = 300):
        self.slack_webhook = slack_webhook or os.getenv("PRODINAMIK_SLACK_WEBHOOK", "")
        self.telegram_token = telegram_token or os.getenv("PRODINAMIK_TELEGRAM_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.getenv("PRODINAMIK_TELEGRAM_CHAT_ID", "")
        self.generic_webhook = generic_webhook or os.getenv("PRODINAMIK_GENERIC_WEBHOOK", "")
        self.min_interval_sec = min_interval_sec
        self.dedup_window_sec = dedup_window_sec

        # Runtime state
        self._history: List[Alert] = []
        self._last_sent: Dict[str, float] = {}  # channel → timestamp
        self._dedup_cache: Dict[str, float] = {}  # alert_id → timestamp
        self._lock = threading.Lock()
        self._handlers: List[Callable[[Alert], None]] = []

    # ── Channels ──

    @property
    def enabled_channels(self) -> List[str]:
        channels = []
        if self.slack_webhook:
            channels.append("slack")
        if self.telegram_token and self.telegram_chat_id:
            channels.append("telegram")
        if self.generic_webhook:
            channels.append("generic")
        return channels

    @property
    def is_configured(self) -> bool:
        return len(self.enabled_channels) > 0

    # ── Send ──

    def send_alert(self, level: str, title: str, message: str = "",
                   metrics: dict = None, source: str = "engine") -> Alert:
        """Create and send an alert to all configured channels"""
        alert = Alert(level, title, message, metrics, source)

        with self._lock:
            # Dedup check (by title+level)
            dedup_key = f"{alert.level}:{alert.title}"
            if dedup_key in self._dedup_cache:
                elapsed = time.time() - self._dedup_cache[dedup_key]
                if elapsed < self.dedup_window_sec:
                    return alert  # Suppressed
            self._dedup_cache[dedup_key] = time.time()
            self._history.append(alert)

        # Send to channels
        threads = []
        for channel in self.enabled_channels:
            t = threading.Thread(target=self._deliver, args=(channel, alert), daemon=True)
            threads.append(t)
            t.start()

        # Custom handlers
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception:
                pass

        return alert

    def _deliver(self, channel: str, alert: Alert):
        """Deliver alert to a single channel with rate limiting"""
        # Rate limit check
        with self._lock:
            last = self._last_sent.get(channel, 0)
            elapsed = time.time() - last
            if elapsed < self.min_interval_sec:
                return  # Rate limited
            self._last_sent[channel] = time.time()

        try:
            if channel == "slack":
                self._send_slack(alert)
            elif channel == "telegram":
                self._send_telegram(alert)
            elif channel == "generic":
                self._send_generic(alert)
        except Exception as e:
            print(f"⚠️ Alert delivery failed ({channel}): {e}")

    # ── Channel Implementations ──

    def _send_slack(self, alert: Alert):
        if not self.slack_webhook:
            return
        payload = alert.to_slack_payload()
        self._webhook_post(self.slack_webhook, payload)

    def _send_telegram(self, alert: Alert):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        text = alert.to_telegram_payload()
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        self._webhook_post(url, payload)

    def _send_generic(self, alert: Alert):
        if not self.generic_webhook:
            return
        payload = alert.to_dict()
        self._webhook_post(self.generic_webhook, payload)

    def _webhook_post(self, url: str, payload: dict) -> bool:
        """POST JSON payload to webhook URL"""
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            print(f"⚠️ Webhook POST failed: {e}")
            return False

    # ── Alertmanager Webhook Receiver ──

    def handle_alertmanager_webhook(self, data: dict):
        """Handle incoming Prometheus Alertmanager webhook"""
        alerts = data.get("alerts", [])
        for am_alert in alerts:
            labels = am_alert.get("labels", {})
            annotations = am_alert.get("annotations", {})
            level = labels.get("severity", "info")
            title = annotations.get("summary", labels.get("alertname", "Unknown"))
            message = annotations.get("description", "")
            status = am_alert.get("status", "firing")

            if status == "firing":
                self.send_alert(
                    level=level,
                    title=f"[Alertmanager] {title}",
                    message=message,
                    source="alertmanager",
                )

    # ── Subscription ──

    def subscribe(self, handler: Callable[[Alert], None]):
        """Register a custom alert handler (e.g., log, DB write)"""
        self._handlers.append(handler)

    # ── Query ──

    def recent(self, limit: int = 10, min_level: str = "info") -> List[Alert]:
        """Get recent alerts, filtered by minimum severity"""
        min_order = SEVERITY_ORDER.get(min_level, 2)
        recent = []
        for alert in reversed(self._history):
            if SEVERITY_ORDER.get(alert.level, 2) <= min_order:
                recent.append(alert)
                if len(recent) >= limit:
                    break
        return recent

    def summary(self) -> dict:
        """Alert summary statistics"""
        counts = {"critical": 0, "warning": 0, "info": 0}
        for alert in self._history:
            counts[alert.level] = counts.get(alert.level, 0) + 1
        return {
            "total_alerts": len(self._history),
            "counts": counts,
            "channels": self.enabled_channels,
            "min_interval_sec": self.min_interval_sec,
        }

    def test(self, channel: str = "slack") -> bool:
        """Send a test alert to verify channel configuration"""
        alert = self.send_alert(
            level="info",
            title="🧪 Test Alert from Prodinamik Engine",
            message="This is a test alert to verify channel configuration.",
            metrics={"test": True, "timestamp": time.time()},
            source="test",
        )
        return bool(alert.id)


# ──────────────────────────────────────────────
# CLI Integration
# ──────────────────────────────────────────────

def alert_config_from_env() -> AlertManager:
    """Create AlertManager from environment variables"""
    return AlertManager(
        slack_webhook=os.getenv("PRODINAMIK_SLACK_WEBHOOK", ""),
        telegram_token=os.getenv("PRODINAMIK_TELEGRAM_TOKEN", ""),
        telegram_chat_id=os.getenv("PRODINAMIK_TELEGRAM_CHAT_ID", ""),
        generic_webhook=os.getenv("PRODINAMIK_GENERIC_WEBHOOK", ""),
    )
