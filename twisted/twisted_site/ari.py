import hashlib
import hmac
import json
from collections.abc import Iterable
from io import StringIO
from typing import Literal
from urllib.error import HTTPError

import requests
from django.conf import settings

from .models import Journal, Project, ProjectShip

ARI_INGEST_ENDPOINT = settings.ARI_INGEST_ENDPOINT
ARI_SIGNING_SECRET = settings.ARI_SIGNING_SECRET


def send_request(method: Literal["GET", "POST"], data=None, endpoint="", jsonify=True):
    if jsonify or data is None:
        data = json.dumps(data)

    if method == "POST":
        key_bytes = ARI_SIGNING_SECRET.encode("utf-8")
        message_bytes = data.encode("utf-8")

        hmac_object = hmac.new(key_bytes, message_bytes, hashlib.sha256)
        hex_signature = hmac_object.hexdigest()
        headers = {
            "X-Ari-Signature": hex_signature,
            "Content-Type": "application/json",
        }
    else:
        message_bytes = None
        headers = {"Authorization": f"Bearer {ARI_SIGNING_SECRET}"}
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
        "program_hours": untracked_time / 60,
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
            "evidence": ["commits", "elapsed", "devlog"],
            "meta": meta,
        },
    )
    resp = r.content
    r.raise_for_status()


def get_project_status(project: Project):
    r = send_request("GET", endpoint=f"/status?external_id=twisted-{project.id}")
    _resp = r.content
    r.raise_for_status()
    return r.json()
