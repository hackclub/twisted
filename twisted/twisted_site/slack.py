from django.conf import settings
from slack_sdk import WebClient

SLACK_TOKEN = settings.SLACK_TOKEN
SLACK_LOG_CHANNEL = settings.SLACK_LOG_CHANNEL

slack_bot = WebClient(token=SLACK_TOKEN)


def log_to_channel(message):
    if settings.DEBUG:
        slack_bot.chat_postMessage(
            channel=SLACK_LOG_CHANNEL, text=message, username="[DEBUG]"
        )
    else:
        slack_bot.chat_postMessage(channel=SLACK_LOG_CHANNEL, text=message)
