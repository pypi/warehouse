# SPDX-License-Identifier: Apache-2.0

"""Tests for the admin user account export serializers."""

import datetime
import json

import pytest

from warehouse.accounts.models import DisableReason
from warehouse.admin import user_export
from warehouse.ip_addresses.models import BanReason
from warehouse.oidc.models import PendingOIDCPublisher

from ...common.db.accounts import (
    EmailFactory,
    RecoveryCodeFactory,
    UserEventFactory,
    UserFactory,
    UserObservationFactory,
    UserTermsOfServiceEngagementFactory,
    UserUniqueLoginFactory,
    WebAuthnFactory,
)
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.macaroons import MacaroonFactory
from ...common.db.observations import ObserverFactory
from ...common.db.oidc import PendingGitHubPublisherFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
    TeamFactory,
    TeamRoleFactory,
)
from ...common.db.packaging import (
    JournalEntryFactory,
    ProhibitedProjectFactory,
    ProjectFactory,
    ProjectObservationFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)
from ...common.db.ses import EmailMessageFactory, EventFactory as SESEventFactory

# Queries issued by a full `export_user` call for a user with rows in every
# section. Pinned so an unbounded or duplicated section query is visible.
# The truncated count is the ceiling: every capped section fills its page and
# pays for the COUNT that gives its true total.
EXPECTED_QUERY_COUNT = 32
EXPECTED_TRUNCATED_QUERY_COUNT = 41


class TestHelpers:
    def test_dt_none(self):
        """A null timestamp serializes as None."""
        assert user_export._dt(None) is None

    def test_dt_value(self):
        """Timestamps serialize as ISO-8601 strings."""
        moment = datetime.datetime(2026, 7, 31, 12, 0, 0, tzinfo=datetime.UTC)
        assert user_export._dt(moment) == "2026-07-31T12:00:00+00:00"

    def test_dt_naive_stamped_utc(self):
        """Naive timestamps (stored UTC) gain an explicit +00:00 offset."""
        moment = datetime.datetime(2026, 7, 31, 12, 0, 0)
        assert user_export._dt(moment) == "2026-07-31T12:00:00+00:00"

    def test_enum_none(self):
        """A null enum serializes as None."""
        assert user_export._enum(None) is None

    def test_enum_value(self):
        """Enums serialize as raw value plus human-readable name."""
        assert user_export._enum(DisableReason.AdminInitiated) == {
            "value": "admin initiated",
            "display": "AdminInitiated",
        }

    def test_ip_ref_none(self):
        """A missing IP record contributes nothing to the lookup."""
        seen: dict = {}
        assert user_export._ip_ref(None, seen) is None
        assert seen == {}

    def test_ip_ref_materializes_once(self, db_session):
        """Repeat references to one address reuse the first materialization."""
        ip = IpAddressFactory.create(ip_address="203.0.113.7")
        seen: dict = {}

        assert user_export._ip_ref(ip, seen) == str(ip.id)
        assert user_export._ip_ref(ip, seen) == str(ip.id)
        assert list(seen) == [str(ip.id)]

    def test_ip_banned(self, db_session):
        """A banned IP record materializes address, hash, geo, and ban data."""
        ip = IpAddressFactory.create(
            ip_address="1.2.3.4",
            geoip_info={"country_code": "US"},
            is_banned=True,
            ban_reason=BanReason.AUTHENTICATION_ATTEMPTS,
            ban_date=datetime.datetime(2026, 1, 1),
        )
        result = user_export._ip(ip)
        assert result == {
            "id": str(ip.id),
            "ip_address": "1.2.3.4",
            "hashed_ip_address": ip.hashed_ip_address,
            "geoip_info": {"country_code": "US"},
            "is_banned": True,
            "ban_reason": {
                "value": "authentication-attempts",
                "display": "AUTHENTICATION_ATTEMPTS",
            },
            "ban_date": user_export._dt(ip.ban_date),
        }


class TestUserSection:
    def test_empty_user(self, db_request):
        """A bare user serializes with all nested keys present and empty."""
        user = UserFactory.create()
        result = user_export._user_section(user, db_request.db, {})

        assert result["id"] == str(user.id)
        assert result["username"] == user.username
        assert result["disabled_for"] is None
        assert result["two_factor"]["webauthn"] == []
        assert result["two_factor"]["recovery_codes"] == []
        assert result["macaroons"] == []
        assert result["unique_logins"] == []
        assert result["account_associations"] == []
        assert result["terms_of_service_engagements"] == []
        # Nothing secret and nothing non-JSON leaks out.
        assert json.dumps(result)
        flat = json.dumps(result)
        assert user.password not in flat

    def test_populated_user(self, db_request):
        """Emails, 2FA metadata, macaroons, and logins all materialize."""
        user = UserFactory.create(
            totp_secret=b"secret", disabled_for=DisableReason.AccountFrozen
        )
        email = EmailFactory.create(user=user, primary=True, verified=True)
        webauthn = WebAuthnFactory.create(user=user)
        recovery_code = RecoveryCodeFactory.create(user=user)
        macaroon = MacaroonFactory.create(user_id=user.id)
        UserUniqueLoginFactory.create(user=user)
        UserTermsOfServiceEngagementFactory.create(user=user)

        result = user_export._user_section(user, db_request.db, {})

        assert result["disabled_for"] == {
            "value": "account frozen",
            "display": "AccountFrozen",
        }
        assert result["two_factor"]["totp"] == {"enabled": True}
        assert result["two_factor"]["webauthn"] == [
            {"id": str(webauthn.id), "label": webauthn.label, "sign_count": 0}
        ]
        assert len(result["two_factor"]["recovery_codes"]) == 1
        assert recovery_code.code not in json.dumps(result)
        assert result["emails"][0]["email"] == email.email
        assert result["macaroons"][0]["id"] == str(macaroon.id)
        assert "key" not in result["macaroons"][0]
        assert len(result["unique_logins"]) == 1
        assert len(result["terms_of_service_engagements"]) == 1
        assert json.dumps(result)

    def test_every_id_is_a_string(self, db_request):
        """Ids are strings throughout, whatever the column type underneath."""
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True)

        result = user_export._user_section(user, db_request.db, {})

        assert isinstance(result["emails"][0]["id"], str)

    def test_macaroon_caveats_are_decoded(self, db_request):
        """Stored caveats are named objects, not tagged positional arrays."""
        user = UserFactory.create()
        MacaroonFactory.create(user_id=user.id, _caveats=[[3, str(user.id)]])

        result = user_export._user_section(user, db_request.db, {})

        assert result["macaroons"][0]["caveats"] == [
            {"type": "RequestUser", "user_id": str(user.id)}
        ]


class TestCaveats:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            pytest.param(
                [3, "some-user-id"],
                {"type": "RequestUser", "user_id": "some-user-id"},
                id="tagged_array_gains_field_names",
            ),
            # Passed through rather than deserialized: the deserializer bills
            # the legacy-caveat metric, which measures live auth traffic.
            pytest.param(
                {"permissions": "user", "version": 1},
                {"type": "legacy", "permissions": "user", "version": 1},
                id="legacy_mapping_passes_through",
            ),
            pytest.param(
                [9999, "mystery"],
                {"type": "unknown", "raw": [9999, "mystery"]},
                id="unknown_tag_keeps_raw_array",
            ),
        ],
    )
    def test_caveat_materializes_with_a_type(self, stored, expected):
        """Every stored caveat shape becomes a named object with a `type`."""
        assert user_export._caveat(stored) == expected


class TestMembershipSections:
    def test_empty(self, db_request):
        """A user with no memberships gets stable empty sections."""
        user = UserFactory.create()
        result = user_export._membership_sections(user, db_request.db)
        for key in (
            "projects",
            "past_projects",
            "prohibited_names",
            "organizations",
            "teams",
        ):
            assert result[key] == {"count": 0, "rows": []}
        assert result["uploads"] == {
            "count": 0,
            "limit": user_export.SECTION_ROW_LIMIT,
            "truncated": False,
        }
        assert result["project_observations"] == {
            "count": 0,
            "limit": user_export.SECTION_ROW_LIMIT,
            "truncated": False,
            "rows": [],
        }
        assert result["deleted_projects"] == {
            "count": 0,
            "journaled_names": 0,
            "limit": user_export.SECTION_ROW_LIMIT,
            "truncated": False,
            "rows": [],
        }

    def test_project_with_collaborators_and_releases(self, db_request):
        """Project rows carry role, co-collaborators, and release summaries."""
        user = UserFactory.create()
        other = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project, role_name="Owner")
        RoleFactory.create(user=other, project=project, role_name="Maintainer")
        first = ReleaseFactory.create(project=project, uploader=user, version="1.0")
        latest = ReleaseFactory.create(
            project=project,
            uploader=user,
            version="2.0",
            created=first.created + datetime.timedelta(days=1),
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["projects"]["count"] == 1
        row = result["projects"]["rows"][0]
        assert row["id"] == str(project.id)
        assert row["role"] == "Owner"
        assert row["invite_status"] is None
        assert row["collaborators"] == [
            {
                "user_id": str(other.id),
                "username": other.username,
                "role_name": "Maintainer",
            }
        ]
        assert row["releases_uploaded"] == {
            "count": 2,
            "first": {
                "version": "1.0",
                "created": user_export._dt(first.created),
                "uploaded_via": first.uploaded_via,
            },
            "latest": {
                "version": "2.0",
                "created": user_export._dt(latest.created),
                "uploaded_via": latest.uploaded_via,
            },
        }
        assert result["past_projects"] == {"count": 0, "rows": []}
        assert result["uploads"] == {
            "count": 2,
            "limit": user_export.SECTION_ROW_LIMIT,
            "truncated": False,
        }
        assert json.dumps(result)

    def test_uploads_cap_at_the_row_limit(self, db_request, monkeypatch):
        """Past the cap, the summary is partial and the section says so."""
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project, role_name="Owner")
        first = ReleaseFactory.create(project=project, uploader=user, version="1.0")
        ReleaseFactory.create(
            project=project,
            uploader=user,
            version="2.0",
            created=first.created + datetime.timedelta(days=1),
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["uploads"] == {"count": 2, "limit": 1, "truncated": True}
        summary = result["projects"]["rows"][0]["releases_uploaded"]
        assert summary["count"] == 1
        assert summary["latest"]["version"] == "1.0"

    def test_invitation_only_project(self, db_request):
        """An open invitation appears with a null role."""
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleInvitationFactory.create(user=user, project=project)

        result = user_export._membership_sections(user, db_request.db)

        row = result["projects"]["rows"][0]
        assert row["role"] is None
        assert row["invite_status"] is not None

    def test_release_summary_carries_upload_client(self, db_request):
        """Release summaries name the client that published, e.g. twine or CI."""
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        ReleaseFactory.create(
            project=project,
            uploader=user,
            version="1.0",
            uploaded_via="twine/6.0.1 CPython/3.14.0",
        )

        result = user_export._membership_sections(user, db_request.db)

        summary = result["projects"]["rows"][0]["releases_uploaded"]
        assert summary["first"]["uploaded_via"] == "twine/6.0.1 CPython/3.14.0"
        assert summary["latest"]["uploaded_via"] == "twine/6.0.1 CPython/3.14.0"

    def test_past_project_from_uploads(self, db_request):
        """Uploads to a project with no current role land in past_projects."""
        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, uploader=user)

        result = user_export._membership_sections(user, db_request.db)

        assert result["projects"] == {"count": 0, "rows": []}
        assert result["past_projects"]["count"] == 1
        row = result["past_projects"]["rows"][0]
        assert row["role"] is None
        assert row["releases_uploaded"]["count"] == 1
        assert row["releases_uploaded"]["first"]["version"] == release.version

    def test_deleted_project_from_journal_with_no_project_row(self, db_request):
        """
        A project name the user journaled with no live ``Project`` row
        becomes a tombstone, since project removal hard-deletes the row.
        """
        user = UserFactory.create()
        JournalEntryFactory.create(
            name="samplepackage", action="remove project", submitted_by=user
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["deleted_projects"]["count"] == 1
        row = result["deleted_projects"]["rows"][0]
        assert row["name"] == "samplepackage"
        assert row["normalized_name"] == "samplepackage"

    @pytest.mark.parametrize(
        "still_a_member",
        [
            pytest.param(True, id="member"),
            # Removing your own role, or deleting your own releases, leaves
            # exactly this state: a journal row on a project that still lives.
            pytest.param(False, id="not_a_member"),
        ],
    )
    def test_deleted_projects_exclude_live_projects(self, db_request, still_a_member):
        """
        A journaled project that still has a row is never a tombstone, and
        membership has no say in it.
        """
        user = UserFactory.create()
        project = ProjectFactory.create(name="livepackage")
        if still_a_member:
            RoleFactory.create(user=user, project=project)
        JournalEntryFactory.create(name="livepackage", submitted_by=user)

        result = user_export._membership_sections(user, db_request.db)

        assert result["deleted_projects"]["count"] == 0
        assert result["deleted_projects"]["rows"] == []

    def test_prohibited_name_for_touched_project(self, db_request):
        """A prohibited name the user journaled shows the verdict details."""
        user = UserFactory.create()
        admin = UserFactory.create()
        JournalEntryFactory.create(
            name="samplepackage", action="remove project", submitted_by=user
        )
        prohibition = ProhibitedProjectFactory.create(
            name="samplepackage", prohibited_by=admin, comment="malware"
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["prohibited_names"]["count"] == 1
        row = result["prohibited_names"]["rows"][0]
        assert row["name"] == "samplepackage"
        assert row["prohibited_by"] == admin.username
        assert row["comment"] == "malware"
        assert row["created"] == user_export._dt(prohibition.created)

    def test_prohibited_name_matches_regardless_of_spelling(self, db_request):
        """
        A prohibition entered in any spelling still matches, because the
        `normalize_blacklist` trigger normalizes the name on write. The
        lookup compares the column directly, so this pins that behavior.
        """
        user = UserFactory.create()
        JournalEntryFactory.create(
            name="Sample.Package", action="remove project", submitted_by=user
        )
        ProhibitedProjectFactory.create(name="Sample.Package")

        result = user_export._membership_sections(user, db_request.db)

        assert result["prohibited_names"]["count"] == 1
        assert result["prohibited_names"]["rows"][0]["name"] == "sample-package"

    def test_prohibited_names_excludes_untouched_projects(self, db_request):
        """A prohibited name unrelated to the user is not included."""
        user = UserFactory.create()
        ProhibitedProjectFactory.create(name="unrelatedpackage")

        result = user_export._membership_sections(user, db_request.db)

        assert result["prohibited_names"] == {"count": 0, "rows": []}

    def test_deleted_projects_cap_at_the_row_limit(self, db_request, monkeypatch):
        """
        Journaled names are capped like every other section. Uncapped they
        would also expand into the `IN` lists for prohibited names and
        orphaned observations, where the bind-parameter ceiling is a hard
        failure rather than a large document.
        """
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        user = UserFactory.create()
        for name, when in (
            ("oldpackage", datetime.datetime(2020, 1, 1)),
            ("newpackage", datetime.datetime(2026, 1, 1)),
        ):
            JournalEntryFactory.create(
                name=name, submitted_by=user, submitted_date=when
            )

        result = user_export._membership_sections(user, db_request.db)

        section = result["deleted_projects"]
        # `count` is what survived the cap; `journaled_names` is the true
        # size of the set the names were drawn from.
        assert section["count"] == 1
        assert section["journaled_names"] == 2
        assert section["limit"] == 1
        assert section["truncated"] is True
        assert [r["name"] for r in section["rows"]] == ["newpackage"]

    def test_deleted_projects_collapses_name_variants(self, db_request):
        """Journal names differing only in case or separator are one tombstone."""
        user = UserFactory.create()
        JournalEntryFactory.create(name="Variant.Name", submitted_by=user)
        JournalEntryFactory.create(name="variant-name", submitted_by=user)

        result = user_export._membership_sections(user, db_request.db)

        assert result["deleted_projects"]["count"] == 1
        row = result["deleted_projects"]["rows"][0]
        assert row["normalized_name"] == "variant-name"

    def test_project_observations_exclude_reregistered_name(self, db_request):
        """
        An observation on someone else's live project that reuses a name the
        user's deleted project had is not attributed to the user.
        """
        user = UserFactory.create()
        deleted = ProjectFactory.create(name="samplepackage")
        own_observation = ProjectObservationFactory.create(
            related=deleted, kind="is_malware"
        )
        JournalEntryFactory.create(
            name="samplepackage", action="remove project", submitted_by=user
        )
        db_request.db.delete(deleted)
        db_request.db.flush()

        # Someone else registers the freed-up name and gets reported too.
        reregistered = ProjectFactory.create(name="samplepackage")
        ProjectObservationFactory.create(related=reregistered, kind="is_spam")

        result = user_export._membership_sections(user, db_request.db)

        assert [r["id"] for r in result["project_observations"]["rows"]] == [
            str(own_observation.id)
        ]

    def test_project_observation_for_live_project(self, db_request):
        """An observation on a project the user holds a role on appears."""
        user = UserFactory.create()
        project = ProjectFactory.create(name="samplepackage")
        RoleFactory.create(user=user, project=project)
        observation = ProjectObservationFactory.create(
            related=project, kind="is_malware"
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["project_observations"]["count"] == 1
        row = result["project_observations"]["rows"][0]
        assert row["id"] == str(observation.id)
        assert row["project_name"] == "samplepackage"
        assert row["related_id"] == str(project.id)
        assert row["kind_detail"] == {"value": "is_malware", "display": "Is Malware"}

    def test_project_observation_survives_project_deletion(self, db_request):
        """
        An observation on a project the user journaled survives project
        removal, even though removal hard-deletes the Project row and nulls
        the observation's related_id.
        """
        user = UserFactory.create()
        project = ProjectFactory.create(name="samplepackage")
        observation = ProjectObservationFactory.create(
            related=project, kind="is_malware"
        )
        JournalEntryFactory.create(
            name="samplepackage", action="remove project", submitted_by=user
        )
        db_request.db.delete(project)
        db_request.db.flush()

        result = user_export._membership_sections(user, db_request.db)

        assert result["project_observations"]["count"] == 1
        row = result["project_observations"]["rows"][0]
        assert row["id"] == str(observation.id)
        assert row["project_name"] == "samplepackage"
        assert row["related_id"] is None

    def test_project_observations_excludes_untouched_projects(self, db_request):
        """An observation on a project the user never touched is not included."""
        user = UserFactory.create()
        ProjectObservationFactory.create(kind="is_malware")

        result = user_export._membership_sections(user, db_request.db)

        assert result["project_observations"]["count"] == 0
        assert result["project_observations"]["rows"] == []

    def test_project_observation_actions_and_verdict(self, db_request):
        """Admin actions flatten to a time-sorted list with a derived verdict."""
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        ProjectObservationFactory.create(
            related=project,
            kind="is_malware",
            actions={
                "1700000060": {"actor": "admin", "action": "remove_malware"},
                "1700000000": {"actor": "admin", "action": "quarantine_release"},
            },
        )

        result = user_export._membership_sections(user, db_request.db)

        row = result["project_observations"]["rows"][0]
        assert [a["action"] for a in row["actions"]] == [
            "quarantine_release",
            "remove_malware",
        ]
        assert row["actions"][0]["at"] == "2023-11-14T22:13:20+00:00"
        assert row["actions"][0]["actor"] == "admin"
        assert row["verdict"] == "true_positive"

    def test_observation_action_fields_are_allowlisted(self, db_request):
        """
        Action entries carry the named fields and nothing else: `created_at`
        is superseded by `at`, and a key a future action writer adds stays
        out until someone puts it in the allowlist deliberately.
        """
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        ProjectObservationFactory.create(
            related=project,
            kind="is_malware",
            actions={
                "1700000000": {
                    "actor": "some-moderator",
                    "action": "remove_release",
                    "reason": "malware in setup.py",
                    "versions": ["1.0"],
                    "created_at": "2023-11-14 22:13:20+00:00",
                    "future_field": "not yet allowlisted",
                }
            },
        )

        result = user_export._membership_sections(user, db_request.db)

        assert result["project_observations"]["rows"][0]["actions"] == [
            {
                "at": "2023-11-14T22:13:20+00:00",
                "actor": "some-moderator",
                "action": "remove_release",
                "reason": "malware in setup.py",
                "versions": ["1.0"],
            }
        ]

    def test_project_observations_cap_at_the_row_limit(self, db_request, monkeypatch):
        """Project observations keep their most recent rows and flag the cap."""
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)
        for _ in range(2):
            ProjectObservationFactory.create(related=project, kind="is_malware")

        result = user_export._membership_sections(user, db_request.db)

        section = result["project_observations"]
        assert section["count"] == 2
        assert section["limit"] == 1
        assert section["truncated"] is True
        assert len(section["rows"]) == 1

    def test_organizations_and_teams(self, db_request):
        """Org and team rows carry the user's role and co-members."""
        user = UserFactory.create()
        other = UserFactory.create()
        org = OrganizationFactory.create()
        OrganizationRoleFactory.create(user=user, organization=org)
        OrganizationRoleFactory.create(user=other, organization=org)
        team = TeamFactory.create(organization=org)
        TeamRoleFactory.create(user=user, team=team)
        TeamRoleFactory.create(user=other, team=team)

        result = user_export._membership_sections(user, db_request.db)

        assert result["organizations"]["count"] == 1
        org_row = result["organizations"]["rows"][0]
        assert org_row["id"] == str(org.id)
        assert [m["username"] for m in org_row["members"]] == [other.username]
        assert result["teams"]["count"] == 1
        team_row = result["teams"]["rows"][0]
        assert team_row["organization"]["id"] == str(org.id)
        assert [m["username"] for m in team_row["members"]] == [other.username]
        assert json.dumps(result)

    def test_organization_invitation_only(self, db_request):
        """An open org invitation appears with a null role and non-null status."""
        user = UserFactory.create()
        org = OrganizationFactory.create()
        OrganizationInvitationFactory.create(user=user, organization=org)

        result = user_export._membership_sections(user, db_request.db)

        assert result["organizations"]["count"] == 1
        org_row = result["organizations"]["rows"][0]
        assert org_row["role"] is None
        assert org_row["invite_status"] is not None
        assert json.dumps(result)


class TestTimelineSection:
    def test_empty(self, db_request):
        """A user with no activity gets an empty timeline with zero counts."""
        user = UserFactory.create()
        result = user_export._timeline_section(user, db_request.db, {})
        assert result["entries"] == []
        assert result["counts"]["total"] == 0
        assert result["email_sent_matched_addresses"] == []
        assert result["email_sent_match_note"] == user_export.EMAIL_SENT_MATCH_NOTE
        assert (
            result["journal_related_match_note"]
            == user_export.JOURNAL_RELATED_MATCH_NOTE
        )
        assert result["limit"] == user_export.SECTION_ROW_LIMIT
        for kind in (
            "event",
            "journal",
            "journal_related",
            "observation_made",
            "observation_received",
            "email_sent",
        ):
            assert result["counts"][kind] == 0
            assert result["truncated"][kind] is False

    def test_kinds_merge_sorted(self, db_request):
        """Events, journals, observations, and sent emails interleave by time."""
        user = UserFactory.create()
        email = EmailFactory.create(user=user, primary=True)
        UserEventFactory.create(
            source=user, tag="account:login:success", additional={"foo": "bar"}
        )
        journal = JournalEntryFactory.create(submitted_by=user)
        UserObservationFactory.create(related=user, kind="account_abuse")
        message = EmailMessageFactory.create(to=email.email)
        SESEventFactory.create(email=message)

        result = user_export._timeline_section(user, db_request.db, {})

        kinds = {e["kind"] for e in result["entries"]}
        assert kinds == {"event", "journal", "observation_received", "email_sent"}
        assert result["counts"]["total"] == 4
        assert result["email_sent_matched_addresses"] == [email.email]
        times = [e["time"] for e in result["entries"]]
        assert times == sorted(times)
        # Common spine on every entry, string-typed ids throughout
        for entry in result["entries"]:
            assert {"kind", "time", "id"} <= entry.keys()
            assert isinstance(entry["id"], str)
        journal_entry = next(e for e in result["entries"] if e["kind"] == "journal")
        assert journal_entry["id"] == str(journal.id)
        assert json.dumps(result)

    def test_sources_cap_at_the_row_limit(self, db_request, monkeypatch):
        """Each source keeps its most recent rows and flags the truncation."""
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        observer = ObserverFactory.create()
        user = UserFactory.create(observer=ObserverFactory.create())
        admin = UserFactory.create()
        email = EmailFactory.create(user=user, primary=True)
        older = datetime.datetime(2020, 1, 1)
        newer = datetime.datetime(2026, 1, 1)
        for when in (older, newer):
            UserEventFactory.create(source=user, tag="account:login:success", time=when)
            JournalEntryFactory.create(
                submitted_by=user, name="samplepackage", submitted_date=when
            )
            JournalEntryFactory.create(
                submitted_by=admin, name="samplepackage", submitted_date=when
            )
            EmailMessageFactory.create(to=email.email, created=when)
            UserObservationFactory.create(
                related=user, observer=observer, kind="account_abuse"
            )
            UserObservationFactory.create(
                related=UserFactory.create(),
                observer=user.observer,
                kind="account_abuse",
            )

        result = user_export._timeline_section(user, db_request.db, {})

        assert result["limit"] == 1
        assert result["counts"] == {
            "event": 2,
            "journal": 2,
            "journal_related": 2,
            "observation_made": 2,
            "observation_received": 2,
            "email_sent": 2,
            "total": 12,
        }
        assert all(result["truncated"].values())
        assert len(result["entries"]) == 6
        assert {
            e["time"]
            for e in result["entries"]
            if e["kind"] in {"event", "journal", "email_sent"}
        } == {user_export._dt(newer)}

    def test_event_entry_shape(self, db_request):
        """Event entries carry tag, verbatim payload, and materialized IP."""
        user = UserFactory.create()
        event = UserEventFactory.create(source=user, tag="account:2fa:totp")

        result = user_export._timeline_section(user, db_request.db, {})

        entry = result["entries"][0]
        assert entry["kind"] == "event"
        assert entry["tag"] == "account:2fa:totp"
        assert entry["id"] == str(event.id)
        assert "ip_address_id" in entry

    def test_journal_entry_shape(self, db_request):
        """Journal entries carry the submitter's username."""
        user = UserFactory.create()
        journal = JournalEntryFactory.create(
            name="samplepackage", action="new release", submitted_by=user
        )

        result = user_export._timeline_section(user, db_request.db, {})

        entry = next(e for e in result["entries"] if e["kind"] == "journal")
        assert entry["id"] == str(journal.id)
        assert entry["submitted_by"] == user.username

    def test_journal_includes_other_submitters_for_touched_project(self, db_request):
        """
        Journal rows from any submitter on a project the user journaled
        appear too, each labeled with its own submitter.
        """
        user = UserFactory.create()
        admin = UserFactory.create()
        own_entry = JournalEntryFactory.create(
            name="samplepackage", action="new release", submitted_by=user
        )
        admin_entry = JournalEntryFactory.create(
            name="samplepackage", action="remove project", submitted_by=admin
        )
        # An entry on a project the user never touched must not appear.
        JournalEntryFactory.create(name="unrelatedpackage", submitted_by=admin)

        result = user_export._timeline_section(user, db_request.db, {})

        journal_entries = {
            e["id"]: e for e in result["entries"] if e["kind"] == "journal"
        }
        assert len(journal_entries) == 2
        assert journal_entries[str(own_entry.id)]["submitted_by"] == user.username
        assert journal_entries[str(admin_entry.id)]["submitted_by"] == admin.username

    def test_own_journals_survive_a_busy_project(self, db_request, monkeypatch):
        """
        Other submitters' rows on a busy project cannot evict the user's own
        journal entries, which are the point of the export.
        """
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        user = UserFactory.create()
        admin = UserFactory.create()
        own = JournalEntryFactory.create(
            name="samplepackage",
            action="new release",
            submitted_by=user,
            submitted_date=datetime.datetime(2015, 1, 1),
        )
        for action in ("project quarantined", "remove project"):
            JournalEntryFactory.create(
                name="samplepackage",
                action=action,
                submitted_by=admin,
                submitted_date=datetime.datetime(2026, 1, 1),
            )

        result = user_export._timeline_section(user, db_request.db, {})

        journals = [e for e in result["entries"] if e["kind"] == "journal"]
        assert str(own.id) in {e["id"] for e in journals}
        assert result["counts"]["journal"] == 1
        assert result["counts"]["journal_related"] == 2
        assert result["truncated"]["journal"] is False
        assert result["truncated"]["journal_related"] is True

    def test_observation_made(self, db_request):
        """Observations the user filed appear with kind_detail expanded."""
        observer = ObserverFactory.create()
        user = UserFactory.create(observer=observer)
        target = UserFactory.create()
        observation = UserObservationFactory.create(
            related=target, observer=observer, kind="account_abuse"
        )

        result = user_export._timeline_section(user, db_request.db, {})

        made = [e for e in result["entries"] if e["kind"] == "observation_made"]
        assert len(made) == 1
        assert made[0]["kind_detail"] == {
            "value": "account_abuse",
            "display": "Account Abuse",
        }
        assert made[0]["related_name"] == observation.related_name

    def test_historical_addresses_are_listed_but_not_matched(self, db_request):
        """
        Addresses the account no longer holds are surfaced from its own event
        log, but mail is not matched on them: `user_emails.email` is unique
        only among live rows, so a released address may belong to someone
        else now, and their mail is not this user's to export.
        """
        user = UserFactory.create()
        current = EmailFactory.create(user=user, primary=True)
        UserEventFactory.create(
            source=user,
            tag="account:email:primary:change",
            additional={
                "old_primary": "released@example.com",
                "new_primary": current.email,
            },
        )
        EmailMessageFactory.create(to="released@example.com")

        result = user_export._timeline_section(user, db_request.db, {})

        assert result["email_addresses_historical"] == ["released@example.com"]
        assert result["email_sent_matched_addresses"] == [current.email]
        assert result["counts"]["email_sent"] == 0

    @pytest.mark.parametrize(
        ("tag", "additional"),
        [
            # The registration address appears only here: `add_email` during
            # registration emits no `account:email:add`.
            pytest.param("account:create", {"email": "past@example.com"}, id="create"),
            pytest.param("account:email:add", {"email": "past@example.com"}, id="add"),
            pytest.param(
                "account:email:remove", {"email": "past@example.com"}, id="remove"
            ),
            pytest.param(
                "account:email:verified",
                {"email": "past@example.com"},
                id="verified",
            ),
            pytest.param(
                "account:email:reverify",
                {"email": "past@example.com"},
                id="reverify",
            ),
            pytest.param("account:email:sent", {"to": "past@example.com"}, id="sent"),
            pytest.param(
                "account:email:primary:change",
                {"old_primary": "past@example.com", "new_primary": "x@example.com"},
                id="primary_change",
            ),
        ],
    )
    def test_every_address_bearing_event_is_harvested(
        self, db_request, tag, additional
    ):
        """
        Any event that names an address contributes to the historical list.
        An admin deleting an email records no event at all, so whichever
        earlier event named it is the only surviving trace.
        """
        user = UserFactory.create()
        UserEventFactory.create(source=user, tag=tag, additional=additional)

        result = user_export._timeline_section(user, db_request.db, {})

        assert "past@example.com" in result["email_addresses_historical"]

    def test_verdict_is_scoped_to_malware_observations(self, db_request):
        """
        The malware triage verdict is not applied to other kinds, where its
        rules ("project removed means true positive") carry no meaning.
        """
        user = UserFactory.create()
        UserObservationFactory.create(related=user, kind="account_abuse")

        result = user_export._timeline_section(user, db_request.db, {})

        entry = next(
            e for e in result["entries"] if e["kind"] == "observation_received"
        )
        assert entry["verdict"] is None
        assert entry["actions"] == []

    def test_observation_received_resolves_observer(self, db_request):
        """Observations about the user materialize the observing user."""
        observer = ObserverFactory.create()
        reporter = UserFactory.create(is_observer=True, observer=observer)
        user = UserFactory.create()
        UserObservationFactory.create(
            related=user, observer=observer, kind="account_abuse"
        )

        result = user_export._timeline_section(user, db_request.db, {})

        received = [e for e in result["entries"] if e["kind"] == "observation_received"]
        assert len(received) == 1
        assert received[0]["observer"]["username"] == reporter.username


class TestExportUser:
    def test_document_shape(self, db_request):
        """The assembled document has the full envelope and all zones."""
        admin = UserFactory.create()
        user = UserFactory.create()
        db_request.user = admin
        db_request.registry.settings["warehouse.commit"] = "deadbeef"

        document = user_export.export_user(user, db_request)

        assert document["export_schema_version"] == "2"
        assert document["generated_by"] == {
            "id": str(admin.id),
            "username": admin.username,
        }
        assert document["warehouse_commit"] == "deadbeef"
        assert document["generated_at"].endswith("+00:00")
        for key in (
            "user",
            "projects",
            "past_projects",
            "prohibited_names",
            "project_observations",
            "organizations",
            "teams",
            "pending_oidc_publishers",
            "timeline",
            "ip_addresses",
        ):
            assert key in document
        assert json.dumps(document)

    def test_ip_addresses_are_deduplicated_into_a_lookup(self, db_request):
        """
        Every IP is materialized once in a top-level lookup, with events and
        logins referring to it by id, so repeat visits from one address are a
        group-by rather than dozens of identical blobs.
        """
        admin = UserFactory.create()
        user = UserFactory.create()
        ip = IpAddressFactory.create(ip_address="198.51.100.9")
        for _ in range(3):
            UserEventFactory.create(
                source=user, tag="account:login:success", ip_address=ip
            )
        UserUniqueLoginFactory.create(user=user, ip_address=ip)
        db_request.user = admin

        document = user_export.export_user(user, db_request)

        assert document["ip_addresses"] == {
            str(ip.id): {
                "id": str(ip.id),
                "ip_address": "198.51.100.9",
                "hashed_ip_address": ip.hashed_ip_address,
                "geoip_info": ip.geoip_info,
                "is_banned": False,
                "ban_reason": None,
                "ban_date": None,
            }
        }
        events = [e for e in document["timeline"]["entries"] if e["kind"] == "event"]
        assert len(events) == 3
        assert {e["ip_address_id"] for e in events} == {str(ip.id)}
        assert all("ip_address" not in e for e in events)
        login = document["user"]["unique_logins"][0]
        assert login["ip_address_id"] == str(ip.id)
        assert "ip_address" not in login

    def test_pending_publishers(self, db_request):
        """Pending trusted publishers added by the user are listed, with
        provider-specific identifying fields in ``specifier``."""
        user = UserFactory.create()
        publisher = PendingGitHubPublisherFactory.create(added_by=user)
        db_request.user = UserFactory.create()

        document = user_export.export_user(user, db_request)

        section = document["pending_oidc_publishers"]
        assert section["count"] == 1
        row = section["rows"][0]
        assert row["id"] == str(publisher.id)
        assert row["project_name"] == publisher.project_name
        assert row["kind"] == publisher.publisher_name
        assert row["url"] == publisher.publisher_url()
        assert row["organization_id"] is None
        assert row["specifier"] == {
            "repository_owner": publisher.repository_owner,
            "repository_name": publisher.repository_name,
            "repository_owner_id": publisher.repository_owner_id,
            "workflow_filename": publisher.workflow_filename,
            "environment": publisher.environment,
        }

    def test_pending_publisher_organization_scoped(self, db_request):
        """A pending publisher registered under an organization carries its id."""
        user = UserFactory.create()
        org = OrganizationFactory.create()
        publisher = PendingGitHubPublisherFactory.create(
            added_by=user, organization_id=org.id
        )
        db_request.user = UserFactory.create()

        document = user_export.export_user(user, db_request)

        row = document["pending_oidc_publishers"]["rows"][0]
        assert row["id"] == str(publisher.id)
        assert row["organization_id"] == str(org.id)

    def test_specifier_fields_cover_all_pending_publisher_kinds(self):
        """Every pending publisher subclass has a specifier field mapping."""
        assert set(user_export._PUBLISHER_SPECIFIER_FIELDS) == set(
            PendingOIDCPublisher.__subclasses__()
        )
        for klass, fields in user_export._PUBLISHER_SPECIFIER_FIELDS.items():
            for field in fields:
                assert hasattr(klass, field)

    def test_constant_query_count(self, db_request, query_recorder, monkeypatch):
        """
        Query count stays fixed as row counts grow (no N+1).

        Both absolute counts are pinned. On the common path no section fills
        its page, so no section pays for a COUNT. Once every section is
        truncated each one adds its COUNT, and that ceiling is pinned too, so
        an accidentally unbounded or double-counted section shows up here.
        """
        admin = UserFactory.create()
        user = UserFactory.create()
        email = EmailFactory.create(user=user, primary=True)
        org = OrganizationFactory.create()
        OrganizationRoleFactory.create(user=user, organization=org)
        team = TeamFactory.create(organization=org)
        TeamRoleFactory.create(user=user, team=team)
        observer = ObserverFactory.create()
        UserObservationFactory.create(
            related=user, observer=observer, kind="account_abuse"
        )
        user.observer = ObserverFactory.create()
        UserObservationFactory.create(
            related=UserFactory.create(), observer=user.observer, kind="account_abuse"
        )
        for _ in range(3):
            project = ProjectFactory.create()
            RoleFactory.create(user=user, project=project)
            RoleFactory.create(user=UserFactory.create(), project=project)
            ReleaseFactory.create(project=project, uploader=user)
            ProjectObservationFactory.create(related=project, kind="is_malware")
            UserEventFactory.create(source=user, tag="account:login:success")
            journal = JournalEntryFactory.create(submitted_by=user)
            JournalEntryFactory.create(submitted_by=admin, name=journal.name)
            EmailMessageFactory.create(to=email.email)
        MacaroonFactory.create(user_id=user.id)
        UserUniqueLoginFactory.create(user=user)
        PendingGitHubPublisherFactory.create(added_by=user)
        db_request.user = admin
        db_request.db.flush()

        db_request.db.expire_all()
        with query_recorder:
            first_count_doc = user_export.export_user(user, db_request)
        baseline = len(query_recorder.queries)
        assert baseline == EXPECTED_QUERY_COUNT
        query_recorder.clear()

        # Double the volume across every section; the query count must not grow.
        OrganizationRoleFactory.create(
            user=user, organization=OrganizationFactory.create()
        )
        TeamRoleFactory.create(user=user, team=TeamFactory.create(organization=org))
        UserObservationFactory.create(
            related=user, observer=observer, kind="account_abuse"
        )
        UserObservationFactory.create(
            related=UserFactory.create(), observer=user.observer, kind="account_abuse"
        )
        for _ in range(3):
            project = ProjectFactory.create()
            RoleFactory.create(user=user, project=project)
            ReleaseFactory.create(project=project, uploader=user)
            ProjectObservationFactory.create(related=project, kind="is_malware")
            UserEventFactory.create(source=user, tag="account:login:success")
            journal = JournalEntryFactory.create(submitted_by=user)
            JournalEntryFactory.create(submitted_by=admin, name=journal.name)
            EmailMessageFactory.create(to=email.email)
        MacaroonFactory.create(user_id=user.id)
        UserUniqueLoginFactory.create(user=user)
        PendingGitHubPublisherFactory.create(added_by=user)
        db_request.db.flush()

        db_request.db.expire_all()
        with query_recorder:
            user_export.export_user(user, db_request)
        assert len(query_recorder.queries) == baseline
        assert first_count_doc["timeline"]["counts"]["total"] > 0
        assert first_count_doc["timeline"]["counts"]["observation_made"] > 0
        query_recorder.clear()

        # Cap every section, so each one pays for its COUNT: the ceiling.
        monkeypatch.setattr(user_export, "SECTION_ROW_LIMIT", 1)
        db_request.db.expire_all()
        with query_recorder:
            truncated_doc = user_export.export_user(user, db_request)
        assert len(query_recorder.queries) == EXPECTED_TRUNCATED_QUERY_COUNT
        assert all(truncated_doc["timeline"]["truncated"].values())
        assert truncated_doc["uploads"]["truncated"] is True
