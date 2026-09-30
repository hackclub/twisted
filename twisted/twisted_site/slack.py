import logging
from typing import Any

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackClientError
from slack_sdk.web.slack_response import SlackResponse

SLACK_TOKEN = settings.SLACK_TOKEN
SLACK_LOG_CHANNEL = settings.SLACK_LOG_CHANNEL

slack_bot = WebClient(token=SLACK_TOKEN)

logger = logging.getLogger(__name__)


def escape_mrkdwn(text: str) -> str:
    """
    Escape user-controlled text for Slack mrkdwn.

    Escaping ``&``, ``<`` and ``>`` neutralizes link spoofing (``<url|label>``)
    as well as broadcast mentions (``<!channel>``/``<!here>``), which Slack only
    parses in their unescaped form.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_blocks(
    *,
    channel: str,
    blocks: list[dict[str, Any]],  # pyrefly: ignore[explicit-any]
    text: str = " ",
    **kwargs: Any,  # noqa: ANN401 # pyrefly: ignore[explicit-any]
) -> SlackResponse:
    return slack_bot.chat_postMessage(channel=channel, text=text, blocks=blocks, **kwargs)


def log_to_channel(message: str) -> None:
    try:
        if settings.DEBUG:
            _ = slack_bot.chat_postMessage(
                channel=SLACK_LOG_CHANNEL,
                text=message,
                username="[DEBUG]",
            )
        else:
            _ = slack_bot.chat_postMessage(channel=SLACK_LOG_CHANNEL, text=message)
    except SlackClientError:
        logger.exception("Failed to log to Slack channel, message %s", message)
