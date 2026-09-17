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

import dataclasses
import datetime
import enum

from collections.abc import Mapping, Sequence, Sized
from typing import Any
from uuid import UUID

from packaging.utils import canonicalize_name
from pyramid.request import Request
from sqlalchemy import Row, Select, desc, func, select
from sqlalchemy.orm import (
    InstrumentedAttribute,
    Session,
    joinedload,
    lazyload,
    selectin_polymorphic,
    selectinload,
)

from warehouse.accounts.models import OAuthAccountAssociation, User, UserUniqueLogin
from warehouse.email.ses.models import EmailMessage
from warehouse.ip_addresses.models import IpAddress
from warehouse.macaroons.caveats import CaveatError, deserialize_obj
from warehouse.macaroons.models import Macaroon
from warehouse.observations.models import (
    OBSERVATION_KIND_MAP,
    Observation,
    ObservationKind,
    Observer,
)
from warehouse.observations.utils import classify_observation
from warehouse.oidc.models import (
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGitLabPublisher,
    PendingGooglePublisher,
    PendingOIDCPublisher,
)
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationRole,
    Team,
    TeamRole,
)
from warehouse.packaging.models import (
    JournalEntry,
    ProhibitedProjectName,
    Project,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
)
from warehouse.utils import now

EXPORT_SCHEMA_VERSION = "2"

# Most-recent rows fetched per unbounded section (timeline sources, uploads).
# Anything older is left out, and the section says so: the true total is
# always reported, alongside a `truncated` flag.
SECTION_ROW_LIMIT = 10_000

# The `email_sent` timeline source reads `ses.emails`, which is pruned on a
# schedule (see `warehouse.email.ses.tasks.cleanup_ses_emails`), so it is a
# recent-delivery window rather than a full history. The durable record of
# mail we sent is the `account:email:sent` event, which is never pruned.
EMAIL_SENT_MATCH_NOTE = (
    "Delivery records are pruned on a schedule, so an empty or short list "
    "means the rows aged out, not that no mail was sent; the "
    "`account:email:sent` events are the durable record. Matched on the "
    "addresses currently on the account: `user_emails.email` is unique only "
    "among live rows, so an address the account has released may belong to "
    "someone else now and is deliberately not matched."
)

# `journals` has no project foreign key, only a name, so "the same project"
# is not expressible there. A name freed by removal and registered again
# carries the new owner's rows under the old name.
JOURNAL_RELATED_MATCH_NOTE = (
    "Matched on project name, which `journals` stores without a project "
    "reference. If a name the user journaled was removed and later "
    "registered by someone else, that later owner's rows appear here too; "
    "`submitted_by` on each entry says whose they are."
)

# Event payloads that name an email address, by the key each one uses. A
# removed address survives nowhere else: the `Email` row is deleted, and the
# admin delete path records no event at all, so whichever of these named it
# is the only remaining trace. `account:create` carries the registration
# address, which never gets an `account:email:add` of its own.
_EMAIL_EVENT_FIELDS = {
    "account:create": ("email",),
    "account:email:add": ("email",),
    "account:email:remove": ("email",),
    "account:email:reverify": ("email",),
    "account:email:sent": ("to",),
    "account:email:verified": ("email",),
    "account:email:primary:change": ("old_primary", "new_primary"),
}


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


def _caveat(caveat: Any) -> dict:
    """
    Materialize one stored caveat as a named object.

    Current caveats are positional arrays led by a numeric tag, which read as
    magic numbers; the registered `Caveat` dataclass supplies the field
    names. The original mapping format is already self-describing, and is
    passed through rather than deserialized so that reading an export does
    not bill `warehouse.macaroon.caveat.legacy`, which measures live auth
    traffic to decide when the legacy format can be dropped.
    """
    if isinstance(caveat, Mapping):
        return {"type": "legacy", **caveat}
    try:
        decoded = deserialize_obj(caveat)
    except CaveatError:
        # An unreadable restriction is still worth seeing verbatim: dropping
        # it would understate what the token was allowed to do.
        return {"type": "unknown", "raw": caveat}
    return {"type": type(decoded).__name__, **dataclasses.asdict(decoded)}


def _ip(ip: IpAddress) -> dict:
    """Materialize an IpAddress row: address, hash, geo, and ban state."""
    return {
        "id": str(ip.id),
        "ip_address": str(ip.ip_address),
        "hashed_ip_address": ip.hashed_ip_address,
        "geoip_info": ip.geoip_info,
        "is_banned": ip.is_banned,
        "ban_reason": _enum(ip.ban_reason),
        "ban_date": _dt(ip.ban_date),
    }


def _ip_ref(ip: IpAddress | None, seen: dict[str, dict]) -> str | None:
    """
    Record an address in the document-wide lookup, returning its id.

    One materialized copy per address rather than one per event: an account
    with hundreds of events usually has a handful of addresses, so pivoting
    on them stops meaning a string comparison across duplicated blobs.
    """
    if ip is None:
        return None
    key = str(ip.id)
    if key not in seen:
        seen[key] = _ip(ip)
    return key


def _user_section(user: User, db: Session, ips: dict[str, dict]) -> dict:
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
                "id": str(e.id),
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
                "caveats": [_caveat(c) for c in m._caveats],
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
                "ip_address_id": _ip_ref(ul.ip_address, ips),
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


# One uploaded release, as selected by `_membership_sections`:
# project_id, version, created, uploaded_via.
_UploadRow = Row[tuple[UUID, str, datetime.datetime, str | None]]


def _release_ref(release: _UploadRow) -> dict:
    """
    One end of a project's upload range.

    `uploaded_via` is the publishing client's user agent, which separates a
    twine upload from a CI action, a script, or the browser.
    """
    return {
        "version": release.version,
        "created": _dt(release.created),
        "uploaded_via": release.uploaded_via,
    }


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
        "first": _release_ref(first),
        "latest": _release_ref(latest),
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
        select(
            Release.project_id, Release.version, Release.created, Release.uploaded_via
        )
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

    # Project removal hard-deletes the row (see `remove_project`), so a name
    # the user journaled can outlive its `Project`. Recovered from the
    # user's own journal rows since those survive the deletion.
    # Capped like every other unbounded section, and for a sharper reason:
    # these names expand into the `IN` lists below for live projects,
    # prohibited names, and orphaned observations, where enough of them stop
    # being a large document and start being a bind-parameter error.
    own_journaled = (
        select(
            JournalEntry.name,
            func.max(JournalEntry.submitted_date).label("last_journaled"),
        )
        .where(
            JournalEntry._submitted_by == user.username, JournalEntry.name.isnot(None)
        )
        .group_by(JournalEntry.name)
    )
    own_journals = db.execute(
        own_journaled.order_by(desc("last_journaled")).limit(SECTION_ROW_LIMIT)
    ).all()
    journaled_total, journaled_truncated = _capped_total(
        db, own_journals, select(func.count()).select_from(own_journaled.subquery())
    )
    # Journal names are stored as entered, so one project can appear under
    # several spellings ("Foo.Bar", "foo-bar"). They collapse to a single
    # tombstone, keeping every spelling for the observation lookup below.
    # The query takes the most recent names, so it reads back to front: the
    # last write per name wins and each tombstone carries the spelling and
    # date of its most recent journal row.
    journaled: dict[str, dict] = {}
    for name, last_journaled in reversed(own_journals):
        entry = journaled.setdefault(canonicalize_name(name), {"spellings": set()})
        entry["spellings"].add(name)
        entry["name"], entry["last_journaled"] = name, last_journaled

    # Membership does not prove a project is gone: a user who removed their
    # own role, or deleted their own releases, has journaled a project that
    # is still very much alive. Only a missing `Project` row is a tombstone.
    live_normalized = (
        set(
            db.scalars(
                select(Project.normalized_name).where(
                    Project.normalized_name.in_(journaled)
                )
            )
        )
        if journaled
        else set()
    )
    deleted_normalized = journaled.keys() - live_normalized
    deleted_rows = [
        {
            "name": journaled[normalized]["name"],
            "normalized_name": normalized,
            "last_journaled": _dt(journaled[normalized]["last_journaled"]),
        }
        for normalized in sorted(deleted_normalized)
    ]
    known_normalized = {p.normalized_name for p in projects.values()}

    # A prohibition can land on any project name the user has touched, live or
    # deleted, so it is checked against the same normalized-name set.
    # `prohibited_project_names.name` is normalized on write by the
    # `normalize_blacklist` trigger, so it compares directly and uses the
    # unique index on the column.
    touched_normalized = known_normalized | journaled.keys()
    prohibited_rows: list[dict] = []
    if touched_normalized:
        prohibited_rows = [
            {
                "name": row.name,
                "created": _dt(row.created),
                "prohibited_by": row.username,
                "comment": row.comment,
                "observation_kind": row.observation_kind,
            }
            for row in db.execute(
                select(
                    ProhibitedProjectName.name,
                    ProhibitedProjectName.created,
                    User.username,
                    ProhibitedProjectName.comment,
                    ProhibitedProjectName.observation_kind,
                )
                .outerjoin(User, ProhibitedProjectName._prohibited_by == User.id)
                .where(ProhibitedProjectName.name.in_(touched_normalized))
                .order_by(ProhibitedProjectName.created)
            )
        ]

    # Project removal nulls the observation's related_id along with the
    # deleted row (see 444353e3eca2_keep_observations_when_related_removed),
    # leaving the `related_name` snapshot as the only link, the same one
    # `Observation.display_name` falls back to. Name matching is confined to
    # those orphaned rows: a live project carries its related_id, so someone
    # else re-registering a freed-up name would otherwise drag their own
    # observations into this user's export.
    # Built by round-tripping a transient `Project` through the same `repr`
    # that `record_observation` stored, rather than spelling the format out
    # here: `Observation.display_name` and the admin observation views
    # already parse it, and a third hardcoded copy would break silently.
    orphan_reprs = {
        repr(Project(name=spelling))
        for entry in journaled.values()
        for spelling in entry["spellings"]
    }
    observed = Project.Observation.related_id.in_(all_ids) | (
        Project.Observation.related_id.is_(None)
        & Project.Observation.related_name.in_(orphan_reprs)
    )
    project_observations: Sequence[Observation] = []
    observations_total, observations_truncated = 0, False
    if all_ids or orphan_reprs:
        project_observations = db.scalars(
            select(Project.Observation)
            .where(observed)
            .order_by(Project.Observation.created.desc(), Project.Observation.id.desc())
            .limit(SECTION_ROW_LIMIT)
        ).all()
        observations_total, observations_truncated = _capped_total(
            db,
            project_observations,
            select(func.count(Project.Observation.id)).where(observed),
        )
    project_observation_rows = [
        {
            "id": str(obs.id),
            "project_name": obs.display_name,
            "created": _dt(obs.created),
            **_observation_fields(obs),
        }
        for obs in project_observations
    ]

    org_roles = (
        db.scalars(
            select(OrganizationRole)
            .where(OrganizationRole.user_id == user.id)
            .options(
                joinedload(OrganizationRole.organization),
                lazyload(OrganizationRole.user),
            )
        )
        .unique()
        .all()
    )
    org_invites = (
        db.scalars(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.user_id == user.id)
            .options(
                joinedload(OrganizationInvitation.organization),
                lazyload(OrganizationInvitation.user),
            )
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
            .options(
                joinedload(TeamRole.team).joinedload(Team.organization),
                lazyload(TeamRole.user),
            )
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
        # `count` is the tombstones present, not a true total: deriving that
        # under truncation would mean checking every journaled name against
        # `projects`, which is the scan the cap exists to avoid. `truncated`
        # says older names went unexamined, and `journaled_names` gives the
        # true size of the set they were drawn from.
        "deleted_projects": {
            "count": len(deleted_rows),
            "journaled_names": journaled_total,
            "limit": SECTION_ROW_LIMIT,
            "truncated": journaled_truncated,
            "rows": deleted_rows,
        },
        "prohibited_names": _wrap(prohibited_rows),
        "project_observations": {
            "count": observations_total,
            "limit": SECTION_ROW_LIMIT,
            "truncated": observations_truncated,
            "rows": project_observation_rows,
        },
        "organizations": _wrap(org_rows),
        "teams": _wrap(team_rows),
        "uploads": {
            "count": uploads_total,
            "limit": SECTION_ROW_LIMIT,
            "truncated": uploads_truncated,
        },
    }


def _observation_kind(kind: str) -> dict:
    """Expand a stored observation-kind string to value plus display name."""
    known = OBSERVATION_KIND_MAP.get(kind)
    return {"value": kind, "display": known.value[1] if known else kind}


# What an action entry may contribute, over and above its `at` timestamp.
# This is every key the admin views write today except `created_at`, which
# `at` supersedes. Named rather than spread so a key a future action writer
# adds stays out of the document until someone adds it here on purpose,
# which is the guarantee the column allowlists give everywhere else here.
_OBSERVATION_ACTION_FIELDS = ("actor", "action", "reason", "versions")


def _observation_actions(actions: dict | None) -> list[dict]:
    """
    Flatten the admin action log into a time-ordered list.

    Stored as a JSONB object keyed by unix timestamp, which reads as an
    unordered blob of magic numbers. The key becomes an `at` field so the
    log scans like every other sequence of events in the document.
    """
    if not actions:
        return []
    return [
        {
            "at": _dt(datetime.datetime.fromtimestamp(int(at), tz=datetime.UTC)),
            **{
                field: action[field]
                for field in _OBSERVATION_ACTION_FIELDS
                if field in action
            },
        }
        for at, action in sorted(actions.items(), key=lambda item: int(item[0]))
    ]


def _observation_fields(obs: Observation) -> dict:
    """Fields common to made and received observation entries."""
    return {
        "kind_detail": _observation_kind(obs.kind),
        "summary": obs.summary,
        "payload": obs.payload,
        "related_name": obs.related_name,
        "related_id": str(obs.related_id) if obs.related_id else None,
        "actions": _observation_actions(obs.actions),
        # `classify_observation` encodes malware-triage rules - a removed
        # project reads as a confirmed report - which say nothing about an
        # account_abuse or account_recovery observation, so the verdict is
        # only offered for the kind it was written for.
        "verdict": (
            classify_observation(obs.actions, obs.related_id)
            if obs.kind == ObservationKind.IsMalware.value[0]
            else None
        ),
    }


def _timeline_section(user: User, db: Session, ips: dict[str, dict]) -> dict:
    """
    All time-shaped records, merged flat and sorted ascending by time.

    Each source is capped at ``SECTION_ROW_LIMIT`` most-recent rows so the
    document stays bounded for long-lived accounts. ``counts`` always holds
    the true totals and ``truncated`` says which sources dropped their older
    rows; both come free unless a source fills its page.
    """
    entries: list[dict] = []
    counts: dict[str, int] = dict.fromkeys(
        (
            "event",
            "journal",
            "journal_related",
            "observation_made",
            "observation_received",
            "email_sent",
        ),
        0,
    )
    truncated: dict[str, bool] = dict.fromkeys(counts, False)

    def _mark(kind: str, rows: Sized, count: Select[tuple[int]]) -> None:
        """Record a source's true total and whether the cap dropped rows."""
        counts[kind], truncated[kind] = _capped_total(db, rows, count)

    events = db.scalars(
        select(User.Event)
        .where(User.Event.source_id == user.id)
        .options(joinedload(User.Event.ip_address))
        .order_by(User.Event.time.desc(), User.Event.id.desc())
        .limit(SECTION_ROW_LIMIT)
    ).all()
    _mark(
        "event",
        events,
        select(func.count(User.Event.id)).where(User.Event.source_id == user.id),
    )
    entries.extend(
        {
            "kind": "event",
            "time": _dt(e.time),
            "id": str(e.id),
            "tag": e.tag,
            "additional": e.additional,
            "ip_address_id": _ip_ref(e.ip_address, ips),
        }
        for e in events
    )

    # Journals come from two sources sharing one entry shape: the user's own
    # rows, and every other submitter's rows on a project name the user has
    # journaled - an admin's "remove project" or "quarantine" entry is
    # exactly the post-freeze signal this timeline exists to surface. They
    # are capped separately so a project busy enough to fill the page (two
    # journal rows per uploaded file) cannot evict the user's own history.
    own = JournalEntry._submitted_by == user.username
    touched_names = select(JournalEntry.name).where(own)
    related = JournalEntry.name.in_(touched_names) & (
        JournalEntry._submitted_by.is_distinct_from(user.username)
    )
    for source, clause in (("journal", own), ("journal_related", related)):
        rows = db.scalars(
            select(JournalEntry)
            .where(clause)
            .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
            .limit(SECTION_ROW_LIMIT)
        ).all()
        _mark(source, rows, select(func.count(JournalEntry.id)).where(clause))
        entries.extend(
            {
                "kind": "journal",
                "time": _dt(j.submitted_date),
                "id": str(j.id),
                "name": j.name,
                "version": j.version,
                "action": j.action,
                "submitted_by": j._submitted_by,
            }
            for j in rows
        )

    made: Sequence[Observation] = []
    # `user.observer` is an association proxy, so reading it walks to the
    # association row and then to the observer, a lazy load each. The
    # association id is already on the user row, and the observer it points
    # at resolves inside the query below.
    if user.observer_association_id is not None:
        filed_by_user = Observation.observer_id == (
            select(Observer.id)
            .where(Observer._association_id == user.observer_association_id)
            .scalar_subquery()
        )
        # Observations the user filed span every observed model, so this
        # queries the polymorphic union rather than User.Observation.
        made = db.scalars(
            select(Observation)
            .where(filed_by_user)
            .order_by(Observation.created.desc(), Observation.id.desc())
            .limit(SECTION_ROW_LIMIT)
        ).all()
        _mark(
            "observation_made",
            made,
            select(func.count(Observation.id)).where(filed_by_user),
        )
    entries.extend(
        {
            "kind": "observation_made",
            "time": _dt(obs.created),
            "id": str(obs.id),
            **_observation_fields(obs),
        }
        for obs in made
    )

    received = db.scalars(
        select(User.Observation)
        .where(User.Observation.related_id == user.id)
        .options(joinedload(User.Observation.observer))
        .order_by(User.Observation.created.desc(), User.Observation.id.desc())
        .limit(SECTION_ROW_LIMIT)
    ).all()
    _mark(
        "observation_received",
        received,
        select(func.count(User.Observation.id)).where(
            User.Observation.related_id == user.id
        ),
    )
    # Observation.observer_id is NOT NULL, so every row has an observer; the
    # Observer's parent user is optional, though (e.g. an API-only observer).
    assoc_ids = {obs.observer._association_id for obs in received}
    observer_parents = (
        {
            u.observer_association_id: u
            for u in db.scalars(
                select(User).where(User.observer_association_id.in_(assoc_ids))
            )
            .unique()
            .all()
        }
        if assoc_ids
        else {}
    )
    for obs in received:
        parent = observer_parents.get(obs.observer._association_id)
        entries.append(
            {
                "kind": "observation_received",
                "time": _dt(obs.created),
                "id": str(obs.id),
                **_observation_fields(obs),
                "observer": {
                    "id": str(obs.observer.id),
                    "username": parent.username if parent else None,
                },
            }
        )

    addresses = [e.email for e in user.emails]
    # Recovered from the events already loaded above, so this costs no query
    # and sees exactly as far back as the event source reaches.
    current = set(addresses)
    historical = sorted(
        {
            address
            for event in events
            for field in _EMAIL_EVENT_FIELDS.get(event.tag, ())
            if (address := (event.additional or {}).get(field))
            and address not in current
        }
    )
    messages: Sequence[EmailMessage] = []
    if addresses:
        messages = db.scalars(
            select(EmailMessage)
            .where(EmailMessage.to.in_(addresses))
            .options(selectinload(EmailMessage.events))
            .order_by(EmailMessage.created.desc(), EmailMessage.id.desc())
            .limit(SECTION_ROW_LIMIT)
        ).all()
        _mark(
            "email_sent",
            messages,
            select(func.count(EmailMessage.id)).where(EmailMessage.to.in_(addresses)),
        )
    entries.extend(
        {
            "kind": "email_sent",
            "time": _dt(m.created),
            "id": str(m.id),
            "status": _enum(m.status),
            "message_id": m.message_id,
            "from": m.from_,
            "to": m.to,
            "subject": m.subject,
            "missing": m.missing,
            "delivery_events": [
                {
                    "id": str(ev.id),
                    "created": _dt(ev.created),
                    "event_type": _enum(ev.event_type),
                    "data": ev.data,
                }
                for ev in m.events
            ],
        }
        for m in messages
    )

    # All warehouse timestamps are stored UTC, so the ISO strings sort
    # chronologically without re-parsing.
    entries.sort(key=lambda e: e["time"] or "")

    counts["total"] = sum(counts.values())
    return {
        "counts": counts,
        "truncated": truncated,
        "limit": SECTION_ROW_LIMIT,
        "entries": entries,
        "email_sent_matched_addresses": addresses,
        "email_addresses_historical": historical,
        "email_sent_match_note": EMAIL_SENT_MATCH_NOTE,
        "journal_related_match_note": JOURNAL_RELATED_MATCH_NOTE,
    }


# Per-kind identifying columns, over and above the common fields already on
# PendingOIDCPublisher (id, project_name, created, added_by_id,
# organization_id). Keyed by class rather than an isinstance/elif chain so
# adding a new provider is a one-line addition here.
_PUBLISHER_SPECIFIER_FIELDS: dict[type[PendingOIDCPublisher], tuple[str, ...]] = {
    PendingGitHubPublisher: (
        "repository_owner",
        "repository_name",
        "repository_owner_id",
        "workflow_filename",
        "environment",
    ),
    PendingGitLabPublisher: (
        "namespace",
        "project",
        "workflow_filepath",
        "environment",
        "issuer_url",
    ),
    PendingGooglePublisher: ("email", "sub"),
    PendingActiveStatePublisher: (
        "organization",
        "activestate_project_name",
        "actor",
        "actor_id",
    ),
}


def _publisher_specifier(publisher: PendingOIDCPublisher) -> dict:
    """The concrete publisher kind's identifying columns, by field name."""
    fields = _PUBLISHER_SPECIFIER_FIELDS.get(type(publisher), ())
    return {field: getattr(publisher, field) for field in fields}


def _pending_publishers_section(user: User, db: Session) -> dict:
    """Pending trusted publishers the user has registered."""
    # PendingOIDCPublisher is joined-table inheritance: str(p) and other
    # subclass attributes (e.g. GitHubPublisherMixin.__str__) live on the
    # subclass table, so a plain lazy load of the base rows would issue one
    # extra SELECT per row. selectin_polymorphic loads all subclass tables
    # up front, in one query per subclass type - a fixed cost regardless of
    # row count.
    pending = db.scalars(
        select(PendingOIDCPublisher)
        .where(PendingOIDCPublisher.added_by_id == user.id)
        .options(
            selectin_polymorphic(
                PendingOIDCPublisher, PendingOIDCPublisher.__subclasses__()
            )
        )
        .order_by(PendingOIDCPublisher.created)
    ).all()
    rows = [
        {
            "id": str(p.id),
            "kind": p.publisher_name,
            "display": str(p),
            "project_name": p.project_name,
            "created": _dt(p.created),
            "added_by_id": str(p.added_by_id),
            "url": p.publisher_url(),
            "organization_id": (str(p.organization_id) if p.organization_id else None),
            "specifier": _publisher_specifier(p),
        }
        for p in pending
    ]
    return _wrap(rows)


def export_user(
    user: User, request: Request, generated_at: datetime.datetime | None = None
) -> dict:
    """
    Assemble the full user account export document.

    The result contains only JSON-native types; ``json.dumps`` needs no
    custom encoder. Callers that need the generation instant for something
    else, like a filename, pass their own ``generated_at``.
    """
    db = request.db
    # Filled in as the sections below reference addresses, and emitted as
    # one lookup keyed by id rather than inline on every row that saw one.
    ips: dict[str, dict] = {}
    return {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": _dt(generated_at or now(tz=True)),
        "generated_by": {
            "id": str(request.user.id),
            "username": request.user.username,
        },
        "warehouse_commit": request.registry.settings.get("warehouse.commit"),
        "user": _user_section(user, db, ips),
        **_membership_sections(user, db),
        "pending_oidc_publishers": _pending_publishers_section(user, db),
        "timeline": _timeline_section(user, db, ips),
        "ip_addresses": ips,
    }
