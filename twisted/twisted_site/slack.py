import os
from typing import Any

from slack_sdk import WebClient


class SlackBot:
    def __init__(
        self,
        token: str | None = None,
        cc_group_id: str | None = None,
    ):
        self.token = token or os.getenv("SLACK_TOKEN")

        if not self.token:
            raise ValueError("SLACK_TOKEN must be set")

        self.client = WebClient(token=self.token)
        self._cc_group_id = cc_group_id or os.getenv("SLACK_CC_GROUP_ID")

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        return self.client.chat_postMessage(
            channel=channel,
            text=text,
            blocks=blocks,
            **kwargs,
        )

    def send_message(
        self,
        *,
        channel: str,
        text: str,
        **kwargs: Any,
    ):
        return self.post_message(
            channel=channel,
            text=text,
            **kwargs,
        )

    def send_blocks(
        self,
        *,
        channel: str,
        blocks: list[dict[str, Any]],
        text: str = " ",
        **kwargs: Any,
    ):
        return self.post_message(
            channel=channel,
            text=text,
            blocks=blocks,
            **kwargs,
        )

    def dm_user(
        self,
        *,
        user: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """
        Send a DM to a Slack user using their U... user ID.

        No D... DM channel ID is required.
        """
        return self.post_message(
            channel=user,
            text=text,
            blocks=blocks,
            **kwargs,
        )

    def dm_user_blocks(
        self,
        *,
        user: str,
        blocks: list[dict[str, Any]],
        text: str = " ",
        **kwargs: Any,
    ):
        """Send Block Kit directly to a user using their U... ID."""
        return self.dm_user(
            user=user,
            text=text,
            blocks=blocks,
            **kwargs,
        )

    def users_info(self, *, user: str):
        return self.client.users_info(user=user)

    def get_user_profile(self, user: str) -> dict[str, Any]:
        response = self.client.users_info(user=user)

        user_data = response["user"] or {}

        profile = user_data.get("profile", {})

        return {
            "id": user_data["id"],
            "name": user_data.get("name"),
            "real_name": (user_data.get("real_name") or profile.get("real_name")),
            "display_name": (profile.get("display_name") or user_data.get("name")),
            "image_24": profile.get("image_24"),
            "image_32": profile.get("image_32"),
            "image_48": profile.get("image_48"),
            "image_72": profile.get("image_72"),
            "image_192": profile.get("image_192"),
            "image_512": profile.get("image_512"),
        }

    def error_log(
        self,
        *,
        channel: str,
        error: str,
        title: str = "Error Log",
        **kwargs: Any,
    ):
        group_id = self._cc_group_id
        mention = f"<@{group_id}>" if group_id else ""

        parent = self.client.chat_postMessage(
            channel=channel,
            text=title,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{title}*",
                    },
                }
            ],
            **kwargs,
        )

        thread_text = f"```{error}```"

        if mention:
            thread_text += f"\n\nCC: {mention}"

        return self.client.chat_postMessage(
            channel=channel,
            thread_ts=parent["ts"],
            text=thread_text,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": thread_text,
                    },
                }
            ],
        )


slack_token = os.getenv("SLACK_TOKEN")
cc_group_id = os.getenv("SLACK_CC_GROUP_ID")

slack_bot = SlackBot(
    token=slack_token,
    cc_group_id=cc_group_id,
)

slack_client = slack_bot.client
