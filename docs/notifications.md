# Notification System

Crazy Pumpkin OS includes a notification system that routes lifecycle events (task starts, completions, failures) and health alerts to external channels. Two providers are supported out of the box: **Slack** and **Email**.

## Supported Providers

### Slack (`SlackWebhookChannel`)

Posts messages to a Slack workspace via an [Incoming Webhook](https://api.slack.com/messaging/webhooks). The `SlackWebhookChannel` class accepts a webhook URL and optional overrides for channel, username, and icon emoji.

**Features:**

- Severity-level emoji prefixes (`:information_source:`, `:warning:`, `:x:`, `:rotating_light:`)
- Automatic retry with back-off on HTTP 429 (rate-limited) responses
- Message batching via `start_batch()` / `flush_batch()`
- Optional channel, username, and icon overrides

### Email (`send_email`)

Sends plain-text email notifications via SMTP using the `send_email` function. Supports both synchronous and asynchronous (thread-pool) sending.

**Features:**

- Configurable SMTP host, port, user, and password
- `starttls()` is called unconditionally on every connection — the code always attempts a STARTTLS upgrade on the SMTP connection before authenticating. There is currently no `smtp_tls` toggle to disable this behaviour. If the SMTP server does not support STARTTLS, an `SMTPNotSupportedError` will be raised. (See the note on `smtp_tls` below.)
- Async variant (`send_email_async`) for use in event loops

## Configuration

Add a `notifications` section to your `config.yaml`. See `examples/config.yaml` for a full template.

### Slack

```yaml
notifications:
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}   # required — Slack incoming webhook URL
    channel: "#alerts"                  # optional — override default channel
    username: "CrazyPumpkin"            # optional — bot display name
    icon_emoji: ":jack_o_lantern:"      # optional — bot icon emoji
```

| Key | Required | Description |
|-----|----------|-------------|
| `webhook_url` | Yes | Slack incoming webhook URL |
| `channel` | No | Channel override (e.g. `#alerts`) |
| `username` | No | Bot display name |
| `icon_emoji` | No | Bot icon emoji (e.g. `:jack_o_lantern:`) |

### Email

Email is configured by passing a settings dict directly to `send_email()`. The expected keys are:

```yaml
# Not a top-level config.yaml section — passed programmatically
smtp_host: "smtp.example.com"
smtp_port: 587
smtp_user: "alerts@example.com"
smtp_password: ${SMTP_PASSWORD}
smtp_tls: true
```

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `smtp_host` | No | `"localhost"` | SMTP server hostname |
| `smtp_port` | No | `587` | SMTP server port |
| `smtp_user` | No | `""` | SMTP login username |
| `smtp_password` | No | `""` | SMTP login password |
| `smtp_tls` | No | *(not implemented)* | Intended to control STARTTLS behaviour. **Currently ignored** — `starttls()` is always called regardless of this setting. The task "Verify and fix email TLS behavior" must be completed before `smtp_tls` is honoured. |

## send_with_retry API

```python
from crazypumpkin.notifications.base import send_with_retry

result: bool = await send_with_retry(
    notifier=channel,
    message={"text": "Hello"},
    max_retries=3,
    base_delay=1.0,
)
```

### Signature

```python
async send_with_retry(
    notifier: Any,
    message: dict,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> bool
```

**Module:** `crazypumpkin.notifications.base`

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `notifier` | `Any` | *(required)* | The notification channel or transport object to send through |
| `message` | `dict` | *(required)* | Message payload to deliver (e.g. `{"text": "..."}`) |
| `max_retries` | `int` | `3` | Maximum number of retry attempts before giving up |
| `base_delay` | `float` | `1.0` | Initial delay in seconds between retries |

### Return Value

Returns `bool` — `True` if the message was delivered successfully, `False` if all retry attempts were exhausted.

### Exponential Backoff Behaviour

`send_with_retry` uses exponential backoff between retry attempts:

1. First retry waits `base_delay` seconds (default: 1.0 s).
2. Each subsequent retry doubles the delay: `base_delay * 2^(attempt - 1)` — i.e. 1 s, 2 s, 4 s, …
3. After `max_retries` failed attempts the function returns `False` instead of raising.

## NotificationRouter

The `NotificationRouter` is the central dispatcher that routes lifecycle events and health reports to all registered notification channels.

```python
from crazypumpkin.notifications import get_router

router = get_router()  # global singleton
```

### `add_channel(channel: NotificationChannel) -> None`

Register a `NotificationChannel` instance. All subsequent events and health reports will be forwarded to this channel.

```python
from crazypumpkin.notifications.slack import SlackWebhookChannel

channel = SlackWebhookChannel(webhook_url="https://hooks.slack.com/services/T.../B.../xxx")
router.add_channel(channel)
```

### `notify_event(event: dict[str, Any]) -> None`

Route a lifecycle event to all registered channels. The `event` dict must contain an `action` key whose value is one of the recognised lifecycle actions: `task_start`, `task_complete`, `task_fail`, `agent_start`, `agent_complete`, `agent_fail`. Events with unrecognised actions are silently ignored.

Optional keys: `timestamp`, `entity_type`, `entity_id`, `agent_id`, `detail`.

```python
router.notify_event({
    "action": "task_complete",
    "entity_id": "developer",
    "detail": "Implemented login endpoint",
})
```

### `notify_health(report: Any) -> None`

Route a health report to all registered channels. The `report` object should have `status`, `message` (or `summary`), and optionally `details` attributes. The `status` is mapped to an alert level: `healthy` → info, `degraded` → warning, `unhealthy` → error, `critical` → critical.

```python
router.notify_health(health_report)
```

### Module-Level Helpers

```python
from crazypumpkin.notifications import get_router, configure_slack, notify

router = get_router()               # global NotificationRouter singleton
configure_slack(config_dict)         # register a Slack channel from config
notify(event_dict)                   # print + route a lifecycle event
```

## Tutorial

Follow these steps to set up and use the notification system.

### 1. Configure Slack in `config.yaml`

Add a `notifications.slack` section to your project's `config.yaml` (see `examples/config.yaml` for a full template):

```yaml
notifications:
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}
    channel: "#agent-alerts"
    username: "CrazyPumpkin"
    icon_emoji: ":jack_o_lantern:"
```

Set the environment variable before running:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../xxx"
```

### 2. Send a Test Message via `SlackWebhookChannel`

```python
from crazypumpkin.notifications.slack import SlackWebhookChannel

channel = SlackWebhookChannel(
    webhook_url="https://hooks.slack.com/services/T.../B.../xxx",
    channel="#agent-alerts",
)

# Send a plain message
channel.send_message("Pipeline completed successfully.")

# Send an alert with severity level
channel.send_alert("Agent failed after 3 attempts", level="error")
```

Both `send_message` and `send_alert` automatically retry up to 3 times on HTTP 429 (rate-limited) responses.

### 3. Send Email via `send_email()`

```python
from crazypumpkin.notifications.email import send_email

send_email(
    to="team@example.com",
    subject="Agent Alert: task failed",
    body="The developer agent failed task #42. Check logs for details.",
    config={
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "alerts@example.com",
        "smtp_password": "secret",
    },
)
```

For async contexts, use `send_email_async` instead:

```python
from crazypumpkin.notifications.email import send_email_async

await send_email_async(
    to="team@example.com",
    subject="Agent Alert: task failed",
    body="The developer agent failed task #42.",
    config={"smtp_host": "smtp.example.com", "smtp_port": 587},
)
```

> **Note:** `starttls()` is always called on the SMTP connection. If your SMTP server does not support STARTTLS, the call will raise `SMTPNotSupportedError`. The `smtp_tls` configuration key is not yet honoured — see the Configuration section above.

### 4. Use `send_with_retry` for Reliable Delivery

For resilient delivery with exponential backoff, use `send_with_retry`:

```python
from crazypumpkin.notifications.base import send_with_retry

success = await send_with_retry(
    notifier=channel,
    message={"text": "Deployment complete — all health checks passing."},
    max_retries=5,
    base_delay=2.0,
)

if not success:
    print("Failed to deliver notification after 5 attempts")
```

This retries with exponential backoff (2 s → 4 s → 8 s → 16 s → 32 s) and returns `True` on success or `False` if all attempts fail.
