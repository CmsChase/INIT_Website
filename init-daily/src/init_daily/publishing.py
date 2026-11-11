import re
import time

import httpx


class PublishError(RuntimeError):
    pass


def validate_webhook(url: str) -> str:
    if not re.fullmatch(r"https://(?:discord\.com|canary\.discord\.com|ptb\.discord\.com)"
                        r"/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]+", url):
        raise PublishError("Configure a standard HTTPS Discord webhook URL (no query parameters)")
    return url + "?wait=true"


def publish(client: httpx.Client, webhook: str, payload: dict) -> str:
    url = validate_webhook(webhook)
    for attempt in range(3):
        try:
            response = client.post(url, json=payload, timeout=25, follow_redirects=False)
            if response.status_code == 429:
                delay = float(response.json().get("retry_after", 1))
                if attempt == 2 or not 0 <= delay <= 15:
                    raise PublishError("Discord rate limited; reservation retained for review")
                time.sleep(delay)
                continue  # A 429 explicitly rejected the request; safe to retry.
            response.raise_for_status()
            message_id = response.json().get("id", "")
            if not isinstance(message_id, str) or not message_id.isdigit() or len(message_id) > 30:
                raise PublishError("Discord did not confirm a message ID; inspect the channel")
            return message_id
        except (httpx.HTTPError, ValueError, TypeError):
            # Timeouts/5xx may occur AFTER Discord saved a message. No blind retry.
            raise PublishError("Discord delivery unconfirmed; reservation retained. Inspect the channel before resolving") from None
    raise PublishError("Discord did not accept the briefing")
