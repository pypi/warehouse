# SPDX-License-Identifier: Apache-2.0

"""
The user account export: an archival JSON copy of a user's account
footprint, assembled for the admin UI.

Every serializer here uses an explicit field allowlist so secret material
(password hashes, TOTP secrets, WebAuthn credentials, recovery codes,
macaroon keys) is excluded by construction, and returns only JSON-native
types so the assembled document dumps with no custom encoder.

See: dev/admin-user-export.md for the document schema.
"""

import datetime
import enum

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from warehouse.accounts.models import OAuthAccountAssociation, User, UserUniqueLogin
from warehouse.ip_addresses.models import IpAddress
from warehouse.macaroons.models import Macaroon

EXPORT_SCHEMA_VERSION = "1"


def _dt(value: datetime.datetime | None) -> str | None:
    """
    Serialize an optional timestamp as an ISO-8601 UTC string.

    Naive datetimes are stored as UTC throughout warehouse; stamp them so
    every timestamp in the document carries an explicit +00:00 offset.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return value.isoformat()


def _enum(value: enum.Enum | None) -> dict | None:
    """Serialize an optional enum as its raw value plus human-readable name."""
    if value is None:
        return None
    return {"value": value.value, "display": value.name}


def _ip(ip: IpAddress | None) -> dict | None:
    """Materialize an IpAddress row: address, hash, geo, and ban state."""
    if ip is None:
        return None
    return {
        "id": str(ip.id),
        "ip_address": str(ip.ip_address),
        "hashed_ip_address": ip.hashed_ip_address,
        "geoip_info": ip.geoip_info,
        "is_banned": ip.is_banned,
        "ban_reason": _enum(ip.ban_reason),
        "ban_date": _dt(ip.ban_date),
    }


def _user_section(user: User, db: Session) -> dict:
    """The identity/credential zone: user row plus nested account records."""
    unique_logins = db.scalars(
        select(UserUniqueLogin)
        .where(UserUniqueLogin.user_id == user.id)
        .options(joinedload(UserUniqueLogin.ip_address))
        .order_by(UserUniqueLogin.created)
    ).all()
    macaroons = db.scalars(
        select(Macaroon).where(Macaroon.user_id == user.id).order_by(Macaroon.created)
    ).all()
    associations = db.scalars(
        select(OAuthAccountAssociation)
        .where(OAuthAccountAssociation._user_id == user.id)
        .order_by(OAuthAccountAssociation.created.desc())
    ).all()
    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.name,
        "date_joined": _dt(user.date_joined),
        "last_login": _dt(user.last_login),
        "password_date": _dt(user.password_date),
        "is_active": user.is_active,
        "is_frozen": user.is_frozen,
        "is_superuser": user.is_superuser,
        "is_support": user.is_support,
        "is_moderator": user.is_moderator,
        "is_psf_staff": user.is_psf_staff,
        "is_observer": user.is_observer,
        "prohibit_password_reset": user.prohibit_password_reset,
        "hide_avatar": user.hide_avatar,
        "disabled_for": _enum(user.disabled_for),
        "emails": [
            {
                "id": e.id,
                "email": e.email,
                "primary": e.primary,
                "verified": e.verified,
                "public": e.public,
                "unverify_reason": _enum(e.unverify_reason),
                "transient_bounces": e.transient_bounces,
                "domain_last_checked": _dt(e.domain_last_checked),
                "domain_last_status": e.domain_last_status,
            }
            for e in user.emails
        ],
        "two_factor": {
            "totp": {"enabled": user.has_totp},
            "webauthn": [
                {"id": str(wa.id), "label": wa.label, "sign_count": wa.sign_count}
                for wa in user.webauthn
            ],
            "recovery_codes": [
                {
                    "id": str(rc.id),
                    "generated": _dt(rc.generated),
                    "burned": _dt(rc.burned),
                }
                for rc in user.recovery_codes
            ],
        },
        # Macaroons here are always user-owned (filtered by user_id above),
        # and the `_user_xor_oidc_publisher_macaroon` check constraint means
        # a user-owned macaroon can never have an oidc_publisher_id set.
        # Publisher-issued macaroons belong to a publisher, not a user, and
        # are out of scope for this section.
        "macaroons": [
            {
                "id": str(m.id),
                "description": m.description,
                "created": _dt(m.created),
                "last_used": _dt(m.last_used),
                "caveats": m._caveats,
                "additional": m.additional,
            }
            for m in macaroons
        ],
        # Select the concrete OAuth subclass directly: a bare base
        # AccountAssociation row is schema-legal (nothing constrains
        # association_type) but is never created by the app and lacks the
        # OAuth columns serialized here.
        "account_associations": [
            {
                "id": str(a.id),
                "association_type": a.association_type,
                "service": a.service,
                "external_user_id": a.external_user_id,
                "external_username": a.external_username,
                "created": _dt(a.created),
                "updated": _dt(a.updated),
                "metadata": a.metadata_,
            }
            for a in associations
        ],
        "terms_of_service_engagements": [
            {
                "id": str(t.id),
                "revision": t.revision,
                "created": _dt(t.created),
                "engagement": _enum(t.engagement),
            }
            for t in user.terms_of_service_engagements
        ],
        "unique_logins": [
            {
                "id": str(ul.id),
                "created": _dt(ul.created),
                "last_used": _dt(ul.last_used),
                "status": _enum(ul.status),
                "expires": _dt(ul.expires),
                "device_information": ul.device_information,
                "ip_address": _ip(ul.ip_address),
            }
            for ul in unique_logins
        ],
    }
