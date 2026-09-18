from dataclasses import dataclass
from typing import Literal

import requests

from .models import Profile

HCA_BASE_URL = "https://auth.hackclub.com/api/v1"


@dataclass
class Address:
    id: str
    first_name: str
    last_name: str
    line_1: str
    line_2: str
    city: str
    state: str
    postal_code: str
    country: str
    phone_number: str
    primary: bool


@dataclass
class Identity:
    id: str
    ysws_eligible: bool
    verification_status: Literal["needs_submission", "pending", "verified", "ineligible"]
    first_name: str
    last_name: str
    primary_email: str
    slack_id: str
    phone_number: str
    birthday: str
    addresses: list[Address]
    primary_address: Address | None


def get_auth_headers(access_token: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    if headers is None:
        headers = {}

    return {"Authorization": f"Bearer {access_token}", **headers}


def get_user_data(profile: Profile) -> Identity:
    access_token = profile.hca_access_token

    headers = get_auth_headers(access_token)  # ty: ignore[invalid-argument-type]

    r = requests.get(HCA_BASE_URL + "/me", headers=headers, timeout=10)
    r.raise_for_status()
    resp = r.json()["identity"]

    addresses: list[Address] = []
    primary_address: Address | None = None
    for address in resp["addresses"]:
        transformed_address = Address(
            id=address.get("id", "None"),
            first_name=address.get("first_name", "None"),
            last_name=address.get("last_name", "None"),
            line_1=address.get("line_1", "None"),
            line_2=address.get("line_2", "None"),
            city=address.get("city", "None"),
            state=address.get("state", "None"),
            postal_code=address.get("postal_code", "None"),
            country=address.get("country", "None"),
            phone_number=address.get("phone_number", "None"),
            primary=address.get("primary", "None"),
        )
        if transformed_address.primary:
            primary_address = transformed_address
        addresses.append(transformed_address)

    return Identity(
        id=resp["id"],
        ysws_eligible=resp["ysws_eligible"],
        verification_status=resp["ysws_eligible"],
        first_name=resp.get("first_name"),
        last_name=resp.get("last_name"),
        primary_email=resp["primary_email"],
        slack_id=resp["slack_id"],
        phone_number=resp["phone_number"],
        birthday=resp["birthday"],
        addresses=addresses,
        primary_address=primary_address,
    )
