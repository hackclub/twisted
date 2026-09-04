from dataclasses import dataclass
from datetime import datetime

import requests

HACKATIME_ROOT_URL = "https://hackatime.hackclub.com"


@dataclass
class MeResponse:
    id: int
    emails: list[str]
    slack_id: str
    gh_username: str
    trust_level: str
    trust_value: int


@dataclass
class HackatimeProject:
    name: str
    total_seconds: int
    most_recent_heartbeat: datetime
    languages: list[str]


def authhelper(access_token, headers=None):
    if headers is None:
        headers = {}

    return {"Authorization": f"Bearer {access_token}", **headers}


def me(access_token) -> MeResponse:
    """Returns information about the authenticated user."""
    resp = requests.get(
        HACKATIME_ROOT_URL + "/api/v1/authenticated/me",
        headers=authhelper(access_token),
    )
    resp.raise_for_status()
    data = resp.json()
    return MeResponse(
        id=data["id"],
        emails=data["emails"],
        slack_id=data["slack_id"],
        gh_username=data["github_username"],
        trust_level=data["trust_factor"]["trust_level"],
        trust_value=data["trust_factor"]["trust_value"],
    )


def projects(
    access_token,
    include_archived=False,
    start: datetime | None = None,
    projects: list[str] | None = None,
) -> list[HackatimeProject]:
    """Returns the user's projects with time totals."""
    resp = requests.get(
        (
            HACKATIME_ROOT_URL + "/api/v1/authenticated/projects"
            f"?include_archived={'true' if include_archived else 'false'}"
            f"&start={str(start.isoformat()) if start is not None else ''}"
            f"&projects={','.join(projects) if projects is not None else ''}"
        ),
        headers=authhelper(access_token),
    )
    resp.raise_for_status()
    data = resp.json()
    hackatime_projects = []
    for project in data["projects"]:
        recent_heartbeat = project["most_recent_heartbeat"]
        dt = datetime.fromisoformat(recent_heartbeat)
        hackatime_projects.append(
            HackatimeProject(
                project["name"],
                total_seconds=project["total_seconds"],
                most_recent_heartbeat=dt,
                languages=project["languages"],
            )
        )
    return hackatime_projects
