# SPDX-License-Identifier: Apache-2.0

"""Tests for the admin user account export serializers."""

import datetime
import json

from warehouse.accounts.models import DisableReason
from warehouse.admin import user_export
from warehouse.ip_addresses.models import BanReason

from ...common.db.accounts import (
    EmailFactory,
    RecoveryCodeFactory,
    UserFactory,
    UserTermsOfServiceEngagementFactory,
    UserUniqueLoginFactory,
    WebAuthnFactory,
)
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.macaroons import MacaroonFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
    TeamFactory,
    TeamRoleFactory,
)
from ...common.db.packaging import (
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)


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

    def test_ip_none(self):
        """A missing IP record serializes as None."""
        assert user_export._ip(None) is None

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
        result = user_export._user_section(user, db_request.db)

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

        result = user_export._user_section(user, db_request.db)

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


class TestMembershipSections:
    def test_empty(self, db_request):
        """A user with no memberships gets stable empty sections."""
        user = UserFactory.create()
        result = user_export._membership_sections(user, db_request.db)
        for key in ("projects", "past_projects", "organizations", "teams"):
            assert result[key] == {"count": 0, "rows": []}
        assert result["uploads"] == {
            "count": 0,
            "limit": user_export.SECTION_ROW_LIMIT,
            "truncated": False,
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
            "first": {"version": "1.0", "created": user_export._dt(first.created)},
            "latest": {"version": "2.0", "created": user_export._dt(latest.created)},
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
