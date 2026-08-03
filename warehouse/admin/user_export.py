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

from collections.abc import Sequence, Sized
from uuid import UUID

from sqlalchemy import Row, Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session, joinedload

from warehouse.accounts.models import OAuthAccountAssociation, User, UserUniqueLogin
from warehouse.ip_addresses.models import IpAddress
from warehouse.macaroons.models import Macaroon
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationRole,
    Team,
    TeamRole,
)
from warehouse.packaging.models import (
    Project,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
)

EXPORT_SCHEMA_VERSION = "1"

# Most-recent rows fetched per unbounded section (timeline sources, uploads).
# Anything older is left out, and the section says so: the true total is
# always reported, alongside a `truncated` flag.
SECTION_ROW_LIMIT = 10_000


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


def _wrap(rows: list[dict]) -> dict:
    """Wrap section rows with a count for drift detection."""
    return {"count": len(rows), "rows": rows}


def _capped_total(
    db: Session, rows: Sized, count: Select[tuple[int]]
) -> tuple[int, bool]:
    """
    A capped fetch's true total, and whether the cap dropped rows.

    A short page is its own total; only a full page can be hiding older
    rows behind the cap, so that is the only case worth a COUNT.
    """
    if len(rows) < SECTION_ROW_LIMIT:
        return len(rows), False
    total = db.scalar(count) or 0
    return total, total > len(rows)


# One uploaded release, as selected by `_membership_sections`.
_UploadRow = Row[tuple[UUID, str, datetime.datetime]]


def _release_summary(releases: Sequence[_UploadRow]) -> dict:
    """
    Summarize a project's releases uploaded by the user: count/first/latest.

    Relies on the uploads query ordering by created, so the list ends are
    the earliest and latest releases.
    """
    if not releases:
        return {"count": 0, "first": None, "latest": None}
    first, latest = releases[0], releases[-1]
    return {
        "count": len(releases),
        "first": {"version": first.version, "created": _dt(first.created)},
        "latest": {"version": latest.version, "created": _dt(latest.created)},
    }


def _co_members(
    db: Session,
    model: type[Role | OrganizationRole | TeamRole],
    group_by: InstrumentedAttribute[UUID],
    ids: set[UUID],
    user_id: UUID,
) -> dict[UUID, list[dict]]:
    """
    Membership rows on the given parents, excluding the user, grouped by
    the parent id column.

    Selects columns rather than entities: `model.user` is a lazy=False
    relationship whose own User.emails collection is lazy=False too, so
    loading the entities would hydrate a full credential-bearing User row
    per email address, for three fields.
    """
    grouped: dict[UUID, list[dict]] = {pid: [] for pid in ids}
    if ids:
        rows = db.execute(
            select(group_by, model.user_id, User.username, model.role_name)
            .join(model.user)
            .where(group_by.in_(ids), model.user_id != user_id)
            .order_by(group_by, User.username)
        ).all()
        for parent_id, member_id, username, role_name in rows:
            grouped[parent_id].append(
                {
                    "user_id": str(member_id),
                    "username": username,
                    "role_name": (
                        _enum(role_name)
                        if isinstance(role_name, enum.Enum)
                        else role_name
                    ),
                }
            )
    return grouped


def _project_row(
    project: Project,
    role_name: str | None,
    invite_status: RoleInvitationStatus | None,
    collaborators: list[dict],
    releases: Sequence[_UploadRow],
) -> dict:
    """One project membership row with collaborators and release summary."""
    return {
        "id": str(project.id),
        "name": project.name,
        "normalized_name": project.normalized_name,
        "lifecycle_status": _enum(project.lifecycle_status),
        "created": _dt(project.created),
        "role": role_name,
        "invite_status": _enum(invite_status),
        "collaborators": collaborators,
        "releases_uploaded": _release_summary(releases),
    }


def _membership_sections(user: User, db: Session) -> dict:
    """
    The relationship zone: projects, orgs, teams, with co-members inline.

    Uploaded releases are capped at ``SECTION_ROW_LIMIT``; the `uploads`
    key carries the true total and flags the cap, since a truncated upload
    set also means partial release summaries and past-project rows.
    """
    # Column selects: Role/RoleInvitation eager-load .user (lazy=False),
    # which itself eager-loads User.emails (lazy=False, a collection), so
    # selecting the entities hydrates rows the document never reads.
    role_by_project: dict[UUID, str] = {
        row.project_id: row.role_name
        for row in db.execute(
            select(Role.project_id, Role.role_name).where(Role.user_id == user.id)
        )
    }
    invite_by_project: dict[UUID, RoleInvitationStatus] = {
        row.project_id: row.invite_status
        for row in db.execute(
            select(RoleInvitation.project_id, RoleInvitation.invite_status).where(
                RoleInvitation.user_id == user.id
            )
        )
    }
    # Release.id breaks ties so the first/latest release of a project is
    # the same row on every run.
    uploads = db.execute(
        select(Release.project_id, Release.version, Release.created)
        .where(Release.uploader_id == user.id)
        .order_by(Release.project_id, Release.created, Release.id)
        .limit(SECTION_ROW_LIMIT)
    ).all()
    uploads_total, uploads_truncated = _capped_total(
        db,
        uploads,
        select(func.count(Release.id)).where(Release.uploader_id == user.id),
    )

    member_ids = set(role_by_project) | set(invite_by_project)
    past_ids = {row.project_id for row in uploads} - member_ids
    all_ids = member_ids | past_ids
    projects = (
        {
            project.id: project
            for project in db.scalars(select(Project).where(Project.id.in_(all_ids)))
        }
        if all_ids
        else {}
    )
    member_projects = {pid: projects[pid] for pid in member_ids}
    past_projects = {pid: projects[pid] for pid in past_ids}

    co_roles = _co_members(db, Role, Role.project_id, all_ids, user.id)

    uploads_by_project: dict[UUID, list[_UploadRow]] = {pid: [] for pid in all_ids}
    for release in uploads:
        uploads_by_project[release.project_id].append(release)

    project_rows = [
        _project_row(
            project,
            role_by_project.get(pid),
            invite_by_project.get(pid),
            co_roles[pid],
            uploads_by_project[pid],
        )
        for pid, project in sorted(
            member_projects.items(), key=lambda kv: kv[1].normalized_name
        )
    ]
    past_rows = [
        _project_row(project, None, None, co_roles[pid], uploads_by_project[pid])
        for pid, project in sorted(
            past_projects.items(), key=lambda kv: kv[1].normalized_name
        )
    ]

    org_roles = (
        db.scalars(
            select(OrganizationRole)
            .where(OrganizationRole.user_id == user.id)
            .options(joinedload(OrganizationRole.organization))
        )
        .unique()
        .all()
    )
    org_invites = (
        db.scalars(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.user_id == user.id)
            .options(joinedload(OrganizationInvitation.organization))
        )
        .unique()
        .all()
    )
    org_ids = {r.organization_id for r in org_roles} | {
        i.organization_id for i in org_invites
    }
    co_org_roles = _co_members(
        db, OrganizationRole, OrganizationRole.organization_id, org_ids, user.id
    )

    org_role_by_id = {r.organization_id: r for r in org_roles}
    org_invite_by_id = {i.organization_id: i for i in org_invites}
    orgs = {r.organization_id: r.organization for r in org_roles}
    orgs.update({i.organization_id: i.organization for i in org_invites})
    org_rows = [
        {
            "id": str(oid),
            "name": org.name,
            "orgtype": _enum(org.orgtype),
            "created": _dt(org.created),
            "role": (
                _enum(org_role_by_id[oid].role_name) if oid in org_role_by_id else None
            ),
            "invite_status": (
                _enum(org_invite_by_id[oid].invite_status)
                if oid in org_invite_by_id
                else None
            ),
            "members": co_org_roles[oid],
        }
        for oid, org in sorted(orgs.items(), key=lambda kv: kv[1].name)
    ]

    team_roles = (
        db.scalars(
            select(TeamRole)
            .where(TeamRole.user_id == user.id)
            .options(joinedload(TeamRole.team).joinedload(Team.organization))
        )
        .unique()
        .all()
    )
    team_ids = {r.team_id for r in team_roles}
    co_team_roles = _co_members(db, TeamRole, TeamRole.team_id, team_ids, user.id)
    team_rows = [
        {
            "id": str(tr.team_id),
            "name": tr.team.name,
            "created": _dt(tr.team.created),
            "organization": {
                "id": str(tr.team.organization_id),
                "name": tr.team.organization.name,
            },
            "role": _enum(tr.role_name),
            "members": co_team_roles[tr.team_id],
        }
        for tr in sorted(team_roles, key=lambda t: t.team.name)
    ]

    return {
        "projects": _wrap(project_rows),
        "past_projects": _wrap(past_rows),
        "organizations": _wrap(org_rows),
        "teams": _wrap(team_rows),
        "uploads": {
            "count": uploads_total,
            "limit": SECTION_ROW_LIMIT,
            "truncated": uploads_truncated,
        },
    }
