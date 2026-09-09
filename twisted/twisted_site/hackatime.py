from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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


def authhelper(access_token: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    if headers is None:
        headers = {}

    return {"Authorization": f"Bearer {access_token}", **headers}


def me(access_token: str) -> MeResponse:
    """Returns information about the authenticated user."""
    resp = requests.get(
        HACKATIME_ROOT_URL + "/api/v1/authenticated/me",
        headers=authhelper(access_token),
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()  # pyrefly: ignore[explicit-any]
    trust_factor: dict[str, Any] = data["trust_factor"]  # pyrefly: ignore[explicit-any]
    return MeResponse(
        id=data["id"],
        emails=data["emails"],
        slack_id=data["slack_id"],
        gh_username=data["github_username"],
        trust_level=trust_factor["trust_level"],
        trust_value=trust_factor["trust_value"],
    )


def projects(
    access_token: str,
    include_archived: bool = False,
    start: datetime | None = datetime(2026, 9, 7, tzinfo=UTC),
    projects: list[str] | None = None,
) -> list[HackatimeProject]:
    """Returns the user's projects with time totals."""
    params = {"include_archived": "true" if include_archived else "false"}
    if start is not None:
        params["start"] = start.isoformat()
    if projects is not None:
        params["projects"] = ",".join(projects)

    resp = requests.get(
        HACKATIME_ROOT_URL + "/api/v1/authenticated/projects",
        params=params,
        headers=authhelper(access_token),
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()  # pyrefly: ignore[explicit-any]
    project_dicts: list[dict[str, Any]] = data["projects"]  # pyrefly: ignore[explicit-any]
    hackatime_projects: list[HackatimeProject] = []
    for project in project_dicts:
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
