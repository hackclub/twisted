import json
import logging
from typing import cast

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from slack_sdk.errors import SlackClientError

from twisted_site.ari import verify_webhook_signature, webhook_secret_configured
from twisted_site.models import (
    PROJECT_NAME_MAX_LENGTH,
    PROJECT_SCREENSHOT_URL_MAX_LENGTH,
    PROJECT_TYPE_CHOICES,
    PROJECT_URL_MAX_LENGTH,
    AriWebhookDelivery,
    Project,
    as_user,
)
from twisted_site.slack import escape_mrkdwn, send_blocks
from twisted_site.validation import sanitize_http_url

logger = logging.getLogger(__name__)

#: Slack block payloads are nested JSON objects; the builders below produce this shape.
SlackBlock = dict[str, str] | dict[str, str | dict[str, str]]

#: Reviewer metadata fields that map to bounded CharFields on ProjectShip.
REVIEW_METADATA_MAX_LENGTH = 255


class _InvalidPayloadError(ValueError):
    """Raised when a signed ARI delivery contains unexpected data."""


def _json_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{name} must be a JSON object"
        raise _InvalidPayloadError(msg)
    return cast("dict[str, object]", value)


def _optional_string(mapping: dict[str, object], key: str, name: str) -> str:
    value = mapping.get(key, "")
    if not isinstance(value, str):
        msg = f"{name} must be a string"
        raise _InvalidPayloadError(msg)
    return value


def _optional_string_list(mapping: dict[str, object], key: str, name: str) -> list[str]:
    value = mapping.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        msg = f"{name} must be a list of strings"
        raise _InvalidPayloadError(msg)
    return cast("list[str]", value)


def _trimmed(value: str, limit: int, name: str) -> str:
    """Trim a model-bound string, logging when it had to shrink."""
    if len(value) <= limit:
        return value
    logger.warning("%s exceeds %d characters; trimming", name, limit)
    return value[:limit]


def _bounded_http_url(value: object, limit: int, name: str) -> str:
    """Sanitize an inbound URL and drop it when it cannot fit the model field."""
    url = sanitize_http_url(value)
    if url != "" and len(url) > limit:
        logger.warning("%s exceeds %d characters; dropping it", name, limit)
        return ""
    return url


def _changes(value: object) -> list[dict[str, str]]:
    """Validate the ``changes`` array shown in ship-update notifications."""
    if value is None:
        return []
    if not isinstance(value, list):
        msg = "changes must be a list"
        raise _InvalidPayloadError(msg)

    changes: list[dict[str, str]] = []
    for index, entry in enumerate(value):
        change = _json_object(cast("object", entry), f"changes[{index}]")
        changes.append(
            {
                "field": _optional_string(change, "field", f"changes[{index}].field"),
                "old_value": _optional_string(change, "old_value", f"changes[{index}].old_value"),
                "new_value": _optional_string(change, "new_value", f"changes[{index}].new_value"),
            },
        )
    return changes


def _notify_maker(project: Project, *, blocks: list[SlackBlock], text: str) -> None:
    """Best-effort maker notification; a Slack outage must not fail the delivery."""
    try:
        _ = send_blocks(channel=as_user(project.user).profile.slack_id, blocks=blocks, text=text)
    except SlackClientError:
        logger.exception("Failed to notify maker about ship update for project %s", project.id)


def _quote_block(value: str) -> str:
    lines = escape_mrkdwn(value).splitlines()
    if len(lines) == 0:
        lines = [""]

    return "\n".join(f"> {line}" for line in lines)


def _build_ship_update_blocks(
    project: Project,
    changes: list[dict[str, str]],
) -> list[SlackBlock]:
    blocks: list[SlackBlock] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":package: Your ship for *{escape_mrkdwn(project.project_name)}* has been updated by a reviewer!",
            },
        },
    ]

    for change in changes:
        blocks.append({"type": "divider"})
        field_name = escape_mrkdwn(change["field"].replace("_", " ").title())
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
            },
        )

    return blocks


def _build_review_changes_blocks(
    project: Project,
    note_to_maker: str,
) -> list[SlackBlock]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":memo: Your ship for *{escape_mrkdwn(project.project_name)}* needs some changes!",
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
    project: Project,
    note_to_maker: str,
) -> list[SlackBlock]:
    blocks: list[SlackBlock] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":tada: Your ship for *{escape_mrkdwn(project.project_name)}* was approved!",
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
            },
        )
    return blocks


def _build_review_rejected_blocks(
    project: Project,
    note_to_maker: str,
) -> list[SlackBlock]:
    blocks: list[SlackBlock] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":x: Your ship for *{escape_mrkdwn(project.project_name)}* was rejected.",
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
            },
        )
    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Feel free to drop us a message over at #twisted-help if you think this is a mistake!",
            },
        },
    )
    return blocks


def _build_review_reverted_blocks(
    project: Project,
) -> list[SlackBlock]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":leftwards_arrow_with_hook: The decision on your ship for *{escape_mrkdwn(project.project_name)}* was reverted, it's back with reviewers.",
            },
        },
    ]


def _build_review_requeued_blocks(
    project: Project,
) -> list[SlackBlock]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":repeat: Your ship for *{escape_mrkdwn(project.project_name)}* is back in the review queue for another look.",
            },
        },
    ]


# Create your views here.
@method_decorator(csrf_exempt, name="dispatch")
class AriView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        body = request.body
        delivery_id = request.headers.get("X-Ari-Delivery-Id", "")

        if not webhook_secret_configured():
            logger.error(
                "ARI_WEBHOOK_SECRET is not set; rejecting inbound ARI webhook delivery",
            )
            return HttpResponse(status=503)

        if not verify_webhook_signature(
            body,
            request.headers.get("X-Ari-Timestamp", ""),
            delivery_id,
            request.headers.get("X-Ari-Signature", ""),
        ):
            return HttpResponse(status=401)

        if (
            delivery_id != ""
            and AriWebhookDelivery.objects.filter(
                delivery_id=delivery_id,
            ).exists()
        ):
            return HttpResponse("Delivery already processed")

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HttpResponseBadRequest("Malformed JSON payload")
        if not isinstance(data, dict):
            return HttpResponseBadRequest("JSON payload must be an object")

        try:
            response = self.handle_event(data)
        except _InvalidPayloadError as error:
            return HttpResponseBadRequest(str(error))

        # Recorded only after the event applied, so a crash still allows ARI's retry.
        if delivery_id != "":
            _ = AriWebhookDelivery.objects.get_or_create(delivery_id=delivery_id)
        return response

    def handle_event(self, data: dict[str, object]) -> HttpResponse:
        external_id = data.get("external_id")
        if not isinstance(external_id, str) or external_id == "":
            return HttpResponseBadRequest("Missing external_id")

        try:
            project_id = int(external_id.removeprefix("twisted-"))
            project = Project.objects.get(id=project_id)
        except (ValueError, Project.DoesNotExist):
            return HttpResponseBadRequest("Invalid external_id")

        event = data.get("event")
        if not isinstance(event, str) or event == "":
            return HttpResponseBadRequest("Missing event")

        if event == "ship.updated":
            return self.handle_ship_updated(project, data)
        if event == "review.changes":
            return self.handle_review_changes(project, data)
        if event == "review.approved":
            return self.handle_review_decision(project, data, status="approved")
        if event == "review.rejected":
            return self.handle_review_decision(project, data, status="rejected")
        if event == "review.reverted":
            return self.handle_review_reset(project, requeued=False)
        if event == "review.requeued":
            return self.handle_review_reset(project, requeued=True)

        return HttpResponse("Event ignored")

    def handle_ship_updated(self, project: Project, data: dict[str, object]) -> HttpResponse:
        ship = _json_object(data.get("ship"), "ship")

        title = _optional_string(ship, "title", "ship.title")
        if title == "":
            msg = "ship.title is required"
            raise _InvalidPayloadError(msg)

        track = _optional_string(ship, "track", "ship.track")
        if track not in PROJECT_TYPE_CHOICES:
            msg = "ship.track is not a known project type"
            raise _InvalidPayloadError(msg)

        project.project_name = _trimmed(title, PROJECT_NAME_MAX_LENGTH, "ship.title")
        project.project_description = _optional_string(ship, "description", "ship.description")
        project.project_type = track
        project.screenshot_url = _bounded_http_url(
            ship.get("thumbnail_url"),
            PROJECT_SCREENSHOT_URL_MAX_LENGTH,
            "ship.thumbnail_url",
        )
        project.repo_url = _bounded_http_url(
            ship.get("repo_url"),
            PROJECT_URL_MAX_LENGTH,
            "ship.repo_url",
        )
        project.playable_url = _bounded_http_url(
            ship.get("demo_url"),
            PROJECT_URL_MAX_LENGTH,
            "ship.demo_url",
        )
        project.hackatime_project_names = _optional_string_list(
            ship,
            "hackatime_projects",
            "ship.hackatime_projects",
        )
        project.save()

        _notify_maker(
            project,
            blocks=_build_ship_update_blocks(project, _changes(data.get("changes"))),
            text=f"Your ship for {escape_mrkdwn(project.project_name)} has been updated by a reviewer!",
        )

        return HttpResponse("Request processed!")

    def handle_review_changes(self, project: Project, data: dict[str, object]) -> HttpResponse:
        decision = _optional_string(data, "decision", "decision")
        if decision != "changes":
            return HttpResponse("Event ignored")

        review = _json_object(data.get("review"), "review")
        note_to_maker = _optional_string(review, "note_to_maker", "review.note_to_maker")

        ship = project.latest_ship()
        if ship is None:
            return HttpResponseBadRequest("Ship not found")

        if ship.status != "requested_changes":
            ship.status = "requested_changes"
        ship.note_to_maker = note_to_maker
        ship.save()

        _notify_maker(
            project,
            blocks=_build_review_changes_blocks(project, note_to_maker),
            text=f"Your ship for {escape_mrkdwn(project.project_name)} needs some changes!",
        )

        return HttpResponse("Request processed!")

    def handle_review_decision(
        self,
        project: Project,
        data: dict[str, object],
        *,
        status: str,
    ) -> HttpResponse:
        review = _json_object(data.get("review"), "review")
        note_to_maker = _optional_string(review, "note_to_maker", "review.note_to_maker")
        audit_note = _optional_string(review, "audit_note", "review.audit_note")

        technical_features = ""
        deflation_reason = ""
        justification = review.get("justification")
        if justification is not None:
            justification_map = _json_object(justification, "review.justification")
            technical_features = _trimmed(
                _optional_string(
                    justification_map,
                    "technical_features",
                    "review.justification.technical_features",
                ),
                REVIEW_METADATA_MAX_LENGTH,
                "review.justification.technical_features",
            )
            deflation_reason = _trimmed(
                _optional_string(
                    justification_map,
                    "deflation_reason",
                    "review.justification.deflation_reason",
                ),
                REVIEW_METADATA_MAX_LENGTH,
                "review.justification.deflation_reason",
            )

        ship = project.latest_ship()
        if ship is None:
            return HttpResponseBadRequest("Ship not found")

        if ship.status != status:
            ship.status = status
        ship.note_to_maker = note_to_maker
        ship.audit_note = audit_note
        if justification is not None:
            ship.technical_features = technical_features
            ship.deflation_reason = deflation_reason
        ship.save()

        if status == "approved":
            blocks = _build_review_approved_blocks(project, note_to_maker)
        else:
            blocks = _build_review_rejected_blocks(project, note_to_maker)
        _notify_maker(
            project,
            blocks=blocks,
            text=f"Your ship for {escape_mrkdwn(project.project_name)} was {status}!",
        )

        return HttpResponse("Request processed!")

    def handle_review_reset(self, project: Project, *, requeued: bool) -> HttpResponse:
        ship = project.latest_ship()
        if ship is None:
            return HttpResponseBadRequest("Ship not found")

        if ship.status != "pending":
            ship.status = "pending"
            ship.save()

        if requeued:
            blocks = _build_review_requeued_blocks(project)
            text = (
                f"Your ship for {escape_mrkdwn(project.project_name)} is back in the review queue."
            )
        else:
            blocks = _build_review_reverted_blocks(project)
            text = (
                f"The decision on your ship for {escape_mrkdwn(project.project_name)} was reverted."
            )
        _notify_maker(project, blocks=blocks, text=text)

        return HttpResponse("Request processed!")
