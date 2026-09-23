from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from slack_sdk.errors import SlackApiError

from twisted_site import slack


class SlackClientTests(SimpleTestCase):
    def test_send_blocks_forwards_payload(self) -> None:
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}]
        with patch("twisted_site.slack.slack_bot.chat_postMessage") as post_message:
            _ = slack.send_blocks(
                channel="C123",
                blocks=blocks,
                text="fallback",
                metadata="value",
            )

        post_message.assert_called_once_with(
            channel="C123",
            blocks=blocks,
            text="fallback",
            metadata="value",
        )

    @override_settings(DEBUG=False)
    def test_production_logging_omits_debug_username(self) -> None:
        with patch("twisted_site.slack.slack_bot.chat_postMessage") as post_message:
            slack.log_to_channel("message")

        post_message.assert_called_once_with(
            channel=slack.SLACK_LOG_CHANNEL,
            text="message",
        )

    @override_settings(DEBUG=True)
    def test_debug_logging_adds_debug_username(self) -> None:
        with patch("twisted_site.slack.slack_bot.chat_postMessage") as post_message:
            slack.log_to_channel("message")

        post_message.assert_called_once_with(
            channel=slack.SLACK_LOG_CHANNEL,
            text="message",
            username="[DEBUG]",
        )

    def test_slack_api_errors_are_logged_without_escaping(self) -> None:
        error = SlackApiError("Slack failed", {"ok": False, "error": "invalid_auth"})
        with (
            patch("twisted_site.slack.slack_bot.chat_postMessage", side_effect=error),
            self.assertLogs("twisted_site.slack", level="ERROR") as logs,
        ):
            result = slack.log_to_channel("message")

        self.assertIsNone(result)
        self.assertIn("Failed to log to Slack channel", logs.output[0])
