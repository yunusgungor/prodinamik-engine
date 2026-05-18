# Configuration

Prodinamik Engine uses a YAML configuration file with environment variable overrides.

## Default Config

```yaml
# prodinamik.yaml
engine:
  base_path: .hermes/
  log_level: INFO
  log_format: text  # text | json

runtime:
  health_interval_sec: 5
  poll_interval_sec: 1
  enable_timeout_watcher: true

server:
  host: 127.0.0.1
  port: 8080

auth:
  keys_path: keys/

metrics:
  enabled: true
```

## Loading Config

```bash
# Default (looks for prodinamik.yaml in current dir)
prodinamik config

# Custom path
prodinamik -c /etc/prodinamik/config.yaml version
```

## Environment Variables

| Variable | Overrides | Example |
|----------|-----------|---------|
| `PRODINAMIK_SLACK_WEBHOOK` | Slack alert webhook URL | `https://hooks.slack.com/...` |
| `PRODINAMIK_TELEGRAM_TOKEN` | Telegram bot token | `123:abc` |
| `PRODINAMIK_TELEGRAM_CHAT_ID` | Telegram chat ID | `-1001234567` |
| `PRODINAMIK_GENERIC_WEBHOOK` | Generic webhook URL | `https://hooks.example.com/...` |
