import json
from typing import Any, cast

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..ari import verify_webhook_signature
from ..models import Project
from ..slack import send_blocks


def _escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _quote_block(value: str) -> str:
    lines = _escape_mrkdwn(value).splitlines()
    if len(lines) == 0:
        lines = [""]

    return "\n".join(f"> {line}" for line in lines)


def _build_ship_update_blocks(
    project: Project, changes: list[dict[str, str]]
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    blocks: list[dict[str, str] | dict[str, str | dict[str, str]]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":package: Your ship for *{_escape_mrkdwn(project.project_name)}* has been updated by a reviewer!",
            },
        },
    ]

    for change in changes:
        blocks.append({"type": "divider"})
        field_name = _escape_mrkdwn(change["field"].replace("_", " ").title())
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{field_name}* changed\n\n"
                        f"*Old:*\n{_quote_block(change['old_value'])}\n\n"
                        f"*New:*\n{_quote_block(change['new_value'])}"
                    ),
                },
            }
        )

    return blocks


def _build_review_changes_blocks(
    project: Project, note_to_maker: str
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":memo: Your ship for *{_escape_mrkdwn(project.project_name)}* needs some changes!",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Note from reviewer:*\n{_quote_block(note_to_maker)}",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Feel free to drop us a message over at #twisted-help if you think this is a mistake!",
            },
        },
    ]


def _build_review_approved_blocks(
    project: Project, note_to_maker: str
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    blocks: list[dict[str, str] | dict[str, str | dict[str, str]]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":tada: Your ship for *{_escape_mrkdwn(project.project_name)}* was approved!",
            },
        },
    ]
    if note_to_maker != "":
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Note from reviewer:*\n{_quote_block(note_to_maker)}",
                },
            }
        )
    return blocks


def _build_review_rejected_blocks(
    project: Project, note_to_maker: str
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    blocks: list[dict[str, str] | dict[str, str | dict[str, str]]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":x: Your ship for *{_escape_mrkdwn(project.project_name)}* was rejected.",
            },
        },
    ]
    if note_to_maker != "":
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Note from reviewer:*\n{_quote_block(note_to_maker)}",
                },
            }
        )
    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Feel free to drop us a message over at #twisted-help if you think this is a mistake!",
            },
        }
    )
    return blocks


def _build_review_reverted_blocks(
    project: Project,
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":leftwards_arrow_with_hook: The decision on your ship for *{_escape_mrkdwn(project.project_name)}* was reverted, it's back with reviewers.",
            },
        },
    ]


def _build_review_requeued_blocks(
    project: Project,
) -> list[dict[str, str] | dict[str, str | dict[str, str]]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":repeat: Your ship for *{_escape_mrkdwn(project.project_name)}* is back in the review queue for another look.",
            },
        },
    ]


# Create your views here.
@method_decorator(csrf_exempt, name="dispatch")
class AriView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        body = request.body

        if not verify_webhook_signature(
            body,
            request.headers.get("X-Ari-Timestamp", ""),
            request.headers.get("X-Ari-Delivery-Id", ""),
            request.headers.get("X-Ari-Signature", ""),
        ):
            return HttpResponse(status=401)

        data = json.loads(body)

        external_id = cast("str | None", data.get("external_id"))
        if external_id in (None, ""):
            return HttpResponseBadRequest("Missing external_id")

        try:
            project_id = int(external_id.removeprefix("twisted-"))
            project = Project.objects.get(id=project_id)
        except (ValueError, Project.DoesNotExist):
            return HttpResponseBadRequest("Invalid external_id")

        event = cast("str | None", data.get("event"))
        if event in (None, ""):
            return HttpResponseBadRequest("Missing event")

        if data["event"] == "ship.updated":
            project.project_name = data["ship"]["title"]
            project.project_description = data["ship"]["description"]
            project.project_type = data["ship"]["track"]
            project.screenshot_url = data["ship"]["thumbnail_url"]
            project.repo_url = data["ship"]["repo_url"]
            project.playable_url = data["ship"]["demo_url"]
            project.hackatime_project_name = data["ship"]["hackatime_projects"][0]
            project.save()
            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_ship_update_blocks(
                    project, cast("list[dict[str, str]]", data["changes"])
                ),
                text=f"Your ship for {project.project_name} has been updated by a reviewer!",
            )

            return HttpResponse("Request processed!")

        if data["event"] == "review.changes":
            if data["decision"] != "changes":
                return HttpResponse("Event ignored")
            note_to_maker = cast(str, data["review"]["note_to_maker"])

            ship = project.latest_ship()
            if ship is None:
                return HttpResponseBadRequest("Ship not found")

            ship.status = "requested_changes"
            ship.note_to_maker = note_to_maker
            ship.save()

            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_review_changes_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} needs some changes!",
            )

            return HttpResponse("Request processed!")

        if data["event"] == "review.approved":
            review = cast("dict[str, Any]", data["review"])
            note_to_maker = cast(str, review.get("note_to_maker", ""))
            raw_justification = review.get("justification")

            ship = project.latest_ship()
            if ship is None:
                return HttpResponseBadRequest("Ship not found")

            ship.status = "approved"
            ship.note_to_maker = note_to_maker
            ship.audit_note = review.get("audit_note", "")
            if isinstance(raw_justification, dict):
                ship.technical_features = raw_justification.get("technical_features", "")
                ship.deflation_reason = raw_justification.get("deflation_reason", "")
            ship.save()

            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_review_approved_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} was approved!",
            )

            return HttpResponse("Request processed!")

        if data["event"] == "review.rejected":
            review = cast("dict[str, Any]", data["review"])
            note_to_maker = cast(str, review.get("note_to_maker", ""))
            raw_justification = review.get("justification")

            ship = project.latest_ship()
            if ship is None:
                return HttpResponseBadRequest("Ship not found")

            ship.status = "rejected"
            ship.note_to_maker = note_to_maker
            ship.audit_note = review.get("audit_note", "")
            if isinstance(raw_justification, dict):
                ship.technical_features = raw_justification.get("technical_features", "")
                ship.deflation_reason = raw_justification.get("deflation_reason", "")
            ship.save()

            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_review_rejected_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} was rejected.",
            )

            return HttpResponse("Request processed!")

        if data["event"] == "review.reverted":
            ship = project.latest_ship()
            if ship is None:
                return HttpResponseBadRequest("Ship not found")

            ship.status = "pending"
            ship.save()

            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_review_reverted_blocks(project),
                text=f"The decision on your ship for {project.project_name} was reverted.",
            )

            return HttpResponse("Request processed!")

        if data["event"] == "review.requeued":
            ship = project.latest_ship()
            if ship is None:
                return HttpResponseBadRequest("Ship not found")

            ship.status = "pending"
            ship.save()

            _ = send_blocks(
                channel=project.user.profile.slack_id,  # pyrefly: ignore[missing-attribute]
                blocks=_build_review_requeued_blocks(project),
                text=f"Your ship for {project.project_name} is back in the review queue.",
            )

            return HttpResponse("Request processed!")

        return HttpResponse("Event ignored")
