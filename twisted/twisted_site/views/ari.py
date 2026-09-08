import json
from django.http import HttpResponseNotAllowed, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from ..ari import verify_webhook_signature
from ..models import ProjectShip, Project
from ..slack import slack_bot


def _escape_mrkdwn(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _quote_block(value):
    lines = _escape_mrkdwn(value).splitlines() or ['']
    return '\n'.join(f'> {line}' for line in lines)


def _build_ship_update_blocks(project, changes):
    blocks = [
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
        field_name = _escape_mrkdwn(change['field'].replace('_', ' ').title())
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{field_name}* changed\n\n"
                    f"*Old:*\n{_quote_block(change['old_value'])}\n\n"
                    f"*New:*\n{_quote_block(change['new_value'])}"
                ),
            },
        })

    return blocks


def _build_review_changes_blocks(project, note_to_maker):
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


def _build_review_approved_blocks(project, note_to_maker):
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":tada: Your ship for *{_escape_mrkdwn(project.project_name)}* was approved!",
            },
        },
    ]
    if note_to_maker:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Note from reviewer:*\n{_quote_block(note_to_maker)}",
            },
        })
    return blocks


def _build_review_rejected_blocks(project, note_to_maker):
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":x: Your ship for *{_escape_mrkdwn(project.project_name)}* was rejected.",
            },
        },
    ]
    if note_to_maker:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Note from reviewer:*\n{_quote_block(note_to_maker)}",
            },
        })
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "Feel free to drop us a message over at #twisted-help if you think this is a mistake!",
        },
    })
    return blocks


def _build_review_reverted_blocks(project):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":leftwards_arrow_with_hook: The decision on your ship for *{_escape_mrkdwn(project.project_name)}* was reverted, it's back with reviewers.",
            },
        },
    ]


def _build_review_requeued_blocks(project):
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
@method_decorator(csrf_exempt, name='dispatch')
class AriView(View):
    def post(self, request):
        body = request.body

        if not verify_webhook_signature(
            body,
            request.headers.get('X-Ari-Timestamp', ''),
            request.headers.get('X-Ari-Delivery-Id', ''),
            request.headers.get('X-Ari-Signature', ''),
        ):
            return HttpResponse(status=401)

        data = json.loads(body)

        external_id = data.get('external_id')
        if not external_id:
            return HttpResponseBadRequest('Missing external_id')

        try:
            project_id = int(external_id.removeprefix('twisted-'))
            project = Project.objects.get(id=project_id)
        except (ValueError, Project.DoesNotExist):  # ty:ignore[unresolved-attribute]
            return HttpResponseBadRequest('Invalid external_id')

        event = data.get('event')
        if not event:
            return HttpResponseBadRequest('Missing event')

        if data['event'] == 'ship.updated':
            project.project_name = data['ship']['title']
            project.project_description = data['ship']['description']
            project.project_type = data['ship']['track']
            project.screenshot_url = data['ship']['thumbnail_url']
            project.repo_url = data['ship']['repo_url']
            project.playable_url = data['ship']['demo_url']
            project.hackatime_project_name = data['ship']['hackatime_projects'][0]
            project.save()
            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_ship_update_blocks(project, data['changes']),
                text=f"Your ship for {project.project_name} has been updated by a reviewer!",
            )

            return HttpResponse('Request processed!')
    
        if data['event'] == 'review.changes':
            if data['decision'] != 'changes':
                return HttpResponse('Event ignored')
            note_to_maker = data['review']['note_to_maker']

            ship:ProjectShip = project.latest_ship()

            ship.status = 'requested_changes'  # ty:ignore[invalid-assignment]
            ship.note_to_maker = note_to_maker
            ship.save()

            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_review_changes_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} needs some changes!",
            )

            return HttpResponse('Request processed!')

        if data['event'] == 'review.approved':
            review = data['review']
            note_to_maker = review.get('note_to_maker', '')
            justification = review.get('justification') or {}

            ship: ProjectShip = project.latest_ship()
            ship.status = 'approved'  # ty:ignore[invalid-assignment]
            ship.note_to_maker = note_to_maker
            ship.audit_note = review.get('audit_note', '')
            ship.technical_features = justification.get('technical_features', '')
            ship.deflation_reason = justification.get('deflation_reason', '')
            ship.save()

            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_review_approved_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} was approved!",
            )

            return HttpResponse('Request processed!')

        if data['event'] == 'review.rejected':
            review = data['review']
            note_to_maker = review.get('note_to_maker', '')
            justification = review.get('justification') or {}

            ship: ProjectShip = project.latest_ship()
            ship.status = 'rejected'  # ty:ignore[invalid-assignment]
            ship.note_to_maker = note_to_maker
            ship.audit_note = review.get('audit_note', '')
            ship.technical_features = justification.get('technical_features', '')
            ship.deflation_reason = justification.get('deflation_reason', '')
            ship.save()

            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_review_rejected_blocks(project, note_to_maker),
                text=f"Your ship for {project.project_name} was rejected.",
            )

            return HttpResponse('Request processed!')

        if data['event'] == 'review.reverted':
            ship: ProjectShip = project.latest_ship()
            ship.status = 'pending'  # ty:ignore[invalid-assignment]
            ship.save()

            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_review_reverted_blocks(project),
                text=f"The decision on your ship for {project.project_name} was reverted.",
            )

            return HttpResponse('Request processed!')

        if data['event'] == 'review.requeued':
            ship: ProjectShip = project.latest_ship()
            ship.status = 'pending'  # ty:ignore[invalid-assignment]
            ship.save()

            slack_bot.send_blocks(
                channel=project.user.profile.slack_id,
                blocks=_build_review_requeued_blocks(project),
                text=f"Your ship for {project.project_name} is back in the review queue.",
            )

            return HttpResponse('Request processed!')

        return HttpResponse('Event ignored')