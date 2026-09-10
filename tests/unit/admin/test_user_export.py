# SPDX-License-Identifier: Apache-2.0

"""Tests for the admin user account export serializers."""

import datetime
import json

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
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)
from ...common.db.ses import EmailMessageFactory, EventFactory as SESEventFactory

# Queries issued by a full `export_user` call for a user with rows in every
# section. Pinned so an unbounded or duplicated section query is visible.
# The truncated count is the ceiling: every capped section fills its page and
# pays for the COUNT that gives its true total.
EXPECTED_QUERY_COUNT = 29
EXPECTED_TRUNCATED_QUERY_COUNT = 35


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


class TestTimelineSection:
    def test_empty(self, db_request):
        """A user with no activity gets an empty timeline with zero counts."""
        user = UserFactory.create()
        result = user_export._timeline_section(user, db_request.db)
        assert result["entries"] == []
        assert result["counts"]["total"] == 0
        assert result["email_sent_matched_addresses"] == []
        assert result["email_sent_match_note"] == user_export.EMAIL_SENT_MATCH_NOTE
        assert result["limit"] == user_export.SECTION_ROW_LIMIT
        for kind in (
            "event",
            "journal",
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

        result = user_export._timeline_section(user, db_request.db)

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
        email = EmailFactory.create(user=user, primary=True)
        older = datetime.datetime(2020, 1, 1)
        newer = datetime.datetime(2026, 1, 1)
        for when in (older, newer):
            UserEventFactory.create(source=user, tag="account:login:success", time=when)
            JournalEntryFactory.create(submitted_by=user, submitted_date=when)
            EmailMessageFactory.create(to=email.email, created=when)
            UserObservationFactory.create(
                related=user, observer=observer, kind="account_abuse"
            )
            UserObservationFactory.create(
                related=UserFactory.create(),
                observer=user.observer,
                kind="account_abuse",
            )

        result = user_export._timeline_section(user, db_request.db)

        assert result["limit"] == 1
        assert result["counts"] == {
            "event": 2,
            "journal": 2,
            "observation_made": 2,
            "observation_received": 2,
            "email_sent": 2,
            "total": 10,
        }
        assert all(result["truncated"].values())
        assert len(result["entries"]) == 5
        assert {
            e["time"]
            for e in result["entries"]
            if e["kind"] in {"event", "journal", "email_sent"}
        } == {user_export._dt(newer)}

    def test_event_entry_shape(self, db_request):
        """Event entries carry tag, verbatim payload, and materialized IP."""
        user = UserFactory.create()
        event = UserEventFactory.create(source=user, tag="account:2fa:totp")

        result = user_export._timeline_section(user, db_request.db)

        entry = result["entries"][0]
        assert entry["kind"] == "event"
        assert entry["tag"] == "account:2fa:totp"
        assert entry["id"] == str(event.id)
        assert "ip_address" in entry

    def test_observation_made(self, db_request):
        """Observations the user filed appear with kind_detail expanded."""
        observer = ObserverFactory.create()
        user = UserFactory.create(observer=observer)
        target = UserFactory.create()
        observation = UserObservationFactory.create(
            related=target, observer=observer, kind="account_abuse"
        )

        result = user_export._timeline_section(user, db_request.db)

        made = [e for e in result["entries"] if e["kind"] == "observation_made"]
        assert len(made) == 1
        assert made[0]["kind_detail"] == {
            "value": "account_abuse",
            "display": "Account Abuse",
        }
        assert made[0]["related_name"] == observation.related_name

    def test_observation_received_resolves_observer(self, db_request):
        """Observations about the user materialize the observing user."""
        observer = ObserverFactory.create()
        reporter = UserFactory.create(is_observer=True, observer=observer)
        user = UserFactory.create()
        UserObservationFactory.create(
            related=user, observer=observer, kind="account_abuse"
        )

        result = user_export._timeline_section(user, db_request.db)

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

        assert document["export_schema_version"] == "1"
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
            "organizations",
            "teams",
            "pending_oidc_publishers",
            "timeline",
        ):
            assert key in document
        assert json.dumps(document)

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
            UserEventFactory.create(source=user, tag="account:login:success")
            JournalEntryFactory.create(submitted_by=user)
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
            UserEventFactory.create(source=user, tag="account:login:success")
            JournalEntryFactory.create(submitted_by=user)
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
