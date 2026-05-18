# Alert Manager

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

**Module:** `engine.alert.py`

## Classes

### `Alert`

Single alert event

**Methods:**

- `__init__(level, title, message, metrics, source)`
- `emoji()`
- `to_dict()`
- `to_slack_payload()`
- `to_telegram_payload()`
- `to_alertmanager_payload()`
  — Format for Prometheus Alertmanager webhook

### `AlertManager`

Central alert manager with webhook delivery.

Supports:
- Slack webhook (Incoming Webhooks API)
- Telegram bot (sendMessage API)
- Generic webhook (custom URL)
- Rate-limited delivery (min_interval_sec)
- Deduplication (same alert suppressed for window_sec)

**Methods:**

- `__init__(slack_webhook, telegram_token, telegram_chat_id, generic_webhook, min_interval_sec, dedup_window_sec)`
- `enabled_channels()`
- `is_configured()`
- `send_alert(level, title, message, metrics, source)`
  — Create and send an alert to all configured channels
- `_deliver(channel, alert)`
  — Deliver alert to a single channel with rate limiting
- `_send_slack(alert)`
- `_send_telegram(alert)`
- `_send_generic(alert)`
- `_webhook_post(url, payload)`
  — POST JSON payload to webhook URL
- `handle_alertmanager_webhook(data)`
  — Handle incoming Prometheus Alertmanager webhook
- `subscribe(handler)`
  — Register a custom alert handler (e.g., log, DB write)
- `recent(limit, min_level)`
  — Get recent alerts, filtered by minimum severity
- `summary()`
  — Alert summary statistics
- `test(channel)`
  — Send a test alert to verify channel configuration

## Functions

### `alert_config_from_env()`

Create AlertManager from environment variables
