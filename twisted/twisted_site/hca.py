from dataclasses import dataclass
from typing import Literal, TypedDict, cast

import requests

HCA_BASE_URL = "https://auth.hackclub.com/api/v1"


class _AddressPayload(TypedDict, total=False):
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


class _IdentityPayload(TypedDict, total=False):
    id: str
    ysws_eligible: bool
    verification_status: Literal["needs_submission", "pending", "verified", "ineligible"]
    first_name: str
    last_name: str
    primary_email: str
    slack_id: str
    phone_number: str
    birthday: str
    addresses: list[_AddressPayload]


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
    verification_status: Literal["needs_submission", "pending", "verified", "ineligible"] | None
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


def get_user_data(access_token: str) -> Identity:
    headers = get_auth_headers(access_token)

    r = requests.get(f"{HCA_BASE_URL}/me", headers=headers, timeout=10)
    r.raise_for_status()
    resp = cast("_IdentityPayload", r.json()["identity"])

    addresses: list[Address] = []
    primary_address: Address | None = None
    addresses_payload: list[_AddressPayload] | None = resp.get("addresses")
    if addresses_payload is None:
        addresses_payload = []
    for address in addresses_payload:
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
            primary=address.get("primary", False),
        )
        if transformed_address.primary:
            primary_address = transformed_address
        addresses.append(transformed_address)

    return Identity(
        id=resp.get("id", "None"),
        ysws_eligible=resp.get("ysws_eligible", False),
        verification_status=resp.get("verification_status"),
        first_name=resp.get("first_name", "None"),
        last_name=resp.get("last_name", "None"),
        primary_email=resp.get("primary_email", "None"),
        slack_id=resp.get("slack_id", "None"),
        phone_number=resp.get("phone_number", "None"),
        birthday=resp.get("birthday", "0000-00-00"),
        addresses=addresses,
        primary_address=primary_address,
    )
