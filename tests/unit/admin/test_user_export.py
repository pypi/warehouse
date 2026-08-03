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
