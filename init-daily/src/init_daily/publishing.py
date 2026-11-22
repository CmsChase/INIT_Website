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


def message_url(webhook: str, message_id: str) -> str:
    validate_webhook(webhook)
    if not isinstance(message_id, str) or not message_id.isdigit() or len(message_id) > 30:
        raise PublishError("A valid stored Discord message ID is required")
    return f"{webhook}/messages/{message_id}"


def message_matches(message: dict, payload: dict) -> bool:
    """Ignore Discord's extra embed metadata, never the displayed text."""
    if not isinstance(message, dict) or message.get("content") != payload.get("content"):
        return False
    actual, expected = message.get("embeds"), payload.get("embeds")
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    return all(isinstance(a, dict) and all(a.get(k) == v for k, v in e.items())
               for a, e in zip(actual, expected))


def get_message(client: httpx.Client, webhook: str, message_id: str) -> dict:
    url = message_url(webhook, message_id)
    try:
        response = client.get(url, timeout=25, follow_redirects=False)
        response.raise_for_status()
        message = response.json()
        if (not isinstance(message, dict) or message.get("id") != message_id
                or message.get("webhook_id") != webhook.split("/")[-2]):
            raise ValueError
        return message
    except (httpx.HTTPError, ValueError, TypeError):
        raise PublishError("Cannot confirm the stored webhook message; no edit attempted") from None


def edit_message(client: httpx.Client, webhook: str, message_id: str, payload: dict) -> dict:
    # Edit accepts neither username nor SUPPRESS_NOTIFICATIONS. Preserve the
    # original message's flags and explicitly disable mention parsing again.
    url = message_url(webhook, message_id)
    body = {"content": payload["content"], "embeds": payload["embeds"], "allowed_mentions": {"parse": []}}
    try:
        response = client.patch(url, json=body, timeout=25, follow_redirects=False)
        response.raise_for_status()
        message = response.json()
        if (message.get("id") != message_id or not message_matches(message, payload)
                or message.get("mention_everyone") or message.get("mentions") or message.get("mention_roles")):
            raise ValueError
        return message
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise PublishError("Discord edit unconfirmed; reservation retained. Inspect the existing message before resolving") from None
