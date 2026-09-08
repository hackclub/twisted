import hashlib
import hmac
import json
import time
from collections.abc import Iterable
from typing import Literal

import requests
from django.conf import settings

from .models import Journal, Project, ProjectShip


ARI_INGEST_ENDPOINT = settings.ARI_INGEST_ENDPOINT
ARI_SIGNING_SECRET = settings.ARI_SIGNING_SECRET
ARI_WEBHOOK_SECRET = settings.ARI_WEBHOOK_SECRET

# Deliveries older than this are rejected, per the "How delivery works" doc.
WEBHOOK_MAX_AGE_SECONDS = 5 * 60


def verify_webhook_signature(body: bytes, timestamp: str, delivery_id: str, signature: str) -> bool:
    """Verifies an outbound delivery from Ari (the X-Ari-Signature/-Timestamp/-Delivery-Id
    headers on review.* and ship.updated webhooks). Signed with ARI_WEBHOOK_SECRET, which is
    separate from ARI_SIGNING_SECRET (that one signs requests we send to Ari)."""
    if not (timestamp and delivery_id and signature):
        return False

    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_MAX_AGE_SECONDS:
            return False
    except ValueError:
        return False

    key_bytes = ARI_WEBHOOK_SECRET.encode("utf-8")
    message_bytes = f"{timestamp}.{delivery_id}.".encode("utf-8") + body
    expected_signature = hmac.new(key_bytes, message_bytes, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def get_hex_signature(content):
    key_bytes = ARI_SIGNING_SECRET.encode("utf-8")
    try:
        message_bytes = content.encode("utf-8")
    except Exception:
        message_bytes = content

    hmac_object = hmac.new(key_bytes, message_bytes, hashlib.sha256)
    hex_signature = hmac_object.hexdigest()

    return hex_signature

def send_request(method: Literal["GET", "POST"], data=None, endpoint="", jsonify=True):
    if jsonify or data is None:
        data = json.dumps(data)

    if method == 'POST':
        headers = {
            "X-Ari-Signature": get_hex_signature(data),
            "Content-Type": "application/json",
        }
        message_bytes = data.encode("utf-8")
    else:
        message_bytes = None
        headers = {
            "Authorization": f"Bearer {ARI_SIGNING_SECRET}"
        }
    req = requests.request(
        method,
        ARI_INGEST_ENDPOINT + endpoint,
        data=message_bytes,
        headers=headers,
    )
    return req

# external_id = "twisted-{project.id}"
def send_ship(ship: ProjectShip):
    if settings.DEBUG_REVIEW:
        return
    external_id = f"twisted-{ship.project.id}"

    untracked_time = 0
    if ship.project.project_type == "hardware":
        for journal in ship.project.journals.filter(type="untracked"):
            untracked_time += journal.reduced_minutes

    maker = {
        "email": ship.project.user.email,
        "name": ship.project.user.profile.slack_username,
        "slack_id": ship.project.user.profile.slack_id,
        "program_hours": untracked_time/60
    }

    title = ship.project.project_name
    description = ship.project.project_description

    repo_url = ship.project.repo_url
    demo_url = ship.project.playable_url

    track = ship.project.project_type
    shipped_at = ship.created_at.isoformat()

    thumbnail_url = ship.project.screenshot_url

    hackatime_projects = [ship.project.hackatime_project_name]

    meta = {
        "project_url": f"https://twisted.hackclub.com/dashboard/?project={ship.project.id}",
        "admin_project_url": f"https://twisted.hackclub.com/admin/projects/{ship.project.id}",
    }

    journals = []
    orm_journals: Iterable[Journal] = ship.project.journals.all()
    for journal in orm_journals:
        content = f"# Journal type: {journal.get_type_display()}\n\n{journal.content}"
        journals.append(
            {
                "at": journal.created_at.isoformat(),
                "minutes": journal.reduced_minutes,
                "text": content,
                "markdown": content,
            }
        )

    r = send_request(
        "POST",
        {
            "external_id": external_id,
            "maker": maker,
            "title": title,
            "description": description,
            "repo_url": repo_url,
            "demo_url": demo_url,
            "track": track,
            "shipped_at": shipped_at,
            "thumbnail_url": thumbnail_url,
            "hackatime_projects": hackatime_projects,
            "evidence": ['commits', 'elapsed', 'devlog'],
            "journals": journals,
            "meta": meta
        },
    )
    resp = r.content
    r.raise_for_status()

def get_project_status(project: Project):
    r = send_request('GET', endpoint=f"/status?external_id=twisted-{project.id}")
    _resp = r.content
    r.raise_for_status()
    return r.json()

# ARI's phases go: (processing | fraud_review | review | under_review) -- reviewer
# hasn't decided yet -- then second_pass -- reviewer decided, an organizer still has
# to confirm it -- then reviewed, where `decision` is locked in. withdrawn/reverted
# are terminal/reset states outside that normal flow.
_ARI_DECISION_TO_SHIP_STATUS = {
    "approved": "approved",
    "changes": "requested_changes",
    "rejected": "rejected",
}


def ship_passes_from_status(status: dict | None) -> tuple[str, str]:
    """Maps an ARI /status response into (first_pass_status, second_pass_status),
    using the PROJECT_SHIP_STATUSES vocabulary (pending/approved/rejected/requested_changes)."""
    if not status:
        return "pending", "pending"

    phase = status.get("phase")
    decision = _ARI_DECISION_TO_SHIP_STATUS.get(status.get("decision"), "pending")

    if phase == "second_pass":
        return decision, "pending"
    if phase == "reviewed":
        return decision, decision
    if phase == "withdrawn":
        return "rejected", "rejected"
    # processing, fraud_review, review, under_review, reverted, or unknown
    return "pending", "pending"
