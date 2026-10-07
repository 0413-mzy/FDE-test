"""Closed onboarding response DTOs: never include password hashes or challenges."""

from typing import Literal

from pydantic import StrictBool, StrictInt

from app.commerce.schemas import DTO, AddressView, Page


class Accepted(DTO):
    accepted: Literal[True]
    simulation: Literal[True]


class Verified(DTO):
    verified: Literal[True]


class Changed(DTO):
    changed: Literal[True]


class Deleted(DTO):
    deleted: Literal[True]


class ProfileView(DTO):
    account_id: str
    username: str
    version: StrictInt
    display_name: str
    phone: str
    email: str | None
    email_verified: StrictBool
    review_enabled: StrictBool


class AddressBookView(DTO):
    id: str
    version: StrictInt
    address: AddressView
    is_default: StrictBool
    created_at: str
    updated_at: str


class MerchantApplicationView(DTO):
    id: str
    version: StrictInt
    state: Literal["PENDING", "APPROVED", "REJECTED", "WITHDRAWN"]
    shop_name: str
    business_scope: str
    contact_name: str
    contact_phone: str
    description: str
    created_at: str
    updated_at: str
    decision_reason: str | None
    shop_id: str | None


RESPONSES = {
    "register": Accepted,
    "verify-email": Verified,
    "verification-request": Accepted,
    "password-reset/request": Accepted,
    "password-reset/confirm": Changed,
    "profile.get": ProfileView,
    "profile": ProfileView,
    "email": Accepted,
    "password": Changed,
    "addresses": Page[AddressBookView],
    "address.create": AddressBookView,
    "address.edit": AddressBookView,
    "address.delete": Deleted,
    "applications": Page[MerchantApplicationView],
    "application.create": MerchantApplicationView,
    "application.withdraw": MerchantApplicationView,
    "review.applications": Page[MerchantApplicationView],
    "application.decision": MerchantApplicationView,
}
