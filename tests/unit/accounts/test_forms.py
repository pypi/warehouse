# SPDX-License-Identifier: Apache-2.0

import datetime
import json

import pytest
import wtforms

from sqlalchemy import select, sql
from webob.multidict import MultiDict

from warehouse.accounts import forms
from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    EmailReputationResult,
    InvalidRecoveryCode,
    NoRecoveryCodes,
    TooManyEmailReputationChecks,
    TooManyFailedLogins,
)
from warehouse.accounts.models import DisableReason, ProhibitedEmailDomain
from warehouse.accounts.services import NullPasswordBreachedService
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.captcha import recaptcha
from warehouse.events.tags import EventTag
from warehouse.ip_addresses.models import BanReason
from warehouse.utils import otp
from warehouse.utils.webauthn import AuthenticationRejectedError

from ...common.db.accounts import (
    EmailFactory,
    ProhibitedEmailDomainFactory,
    ProhibitedUsernameFactory,
    UserFactory,
)

# A verdict that implicates the whole domain: disposable, with the provider
# name UserCheck only returns for a domain it knows as a disposable service.
DISPOSABLE_DOMAIN_VERDICT = EmailReputationResult(
    disposable=True,
    public_domain=False,
    relay_domain=False,
    disposable_provider="MailToWin",
)


@pytest.fixture
def user(db_session):
    """A user named ``my_username`` whose password is ``pw``."""
    return UserFactory.create(username="my_username", clear_pwd="pw")


@pytest.fixture
def breach_service():
    return NullPasswordBreachedService()


def _recaptcha_service(request, *, enabled):
    key = "fake-key" if enabled else None
    return recaptcha.Service(
        request=request,
        script_src_url="//www.recaptcha.net/recaptcha/api.js",
        site_key=key,
        secret_key=key,
    )


@pytest.fixture
def captcha_service(pyramid_request):
    return _recaptcha_service(pyramid_request, enabled=False)


@pytest.fixture
def enabled_captcha_service(pyramid_request):
    return _recaptcha_service(pyramid_request, enabled=True)


@pytest.fixture
def banned_request(db_request):
    """A request whose IP address is banned."""
    db_request.ip_address.is_banned = True
    db_request.ip_address.ban_reason = BanReason.AUTHENTICATION_ATTEMPTS
    db_request.ip_address.ban_date = sql.func.now()
    return db_request


@pytest.fixture
def remote_check_form(db_request, user_service, captcha_service, breach_service):
    """
    Build a RegistrationForm whose non-email fields all validate, so that
    form.validate() reaches the remote reputation check.
    """

    def _make(email):
        return forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict(
                {
                    "username": "myusername",
                    "new_password": "mysupersecurepassword1!",
                    "password_confirm": "mysupersecurepassword1!",
                    "email": email,
                    "acceptable_use": "y",
                }
            ),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )

    return _make


class TestLoginForm:
    def test_validate(self, db_request, user_service, breach_service, user):
        form = forms.LoginForm(
            MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert form.request is db_request
        assert form.user_service is user_service
        assert form.breach_service is breach_service
        assert form.validate(), str(form.errors)

    def test_validate_username_with_null_bytes(
        self, pyramid_config, pyramid_request, user_service, breach_service, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username\0"}),
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert str(form.username.errors.pop()) == "Null bytes are not allowed."
        find_userid.assert_not_called()

    @pytest.mark.parametrize(
        "email_username",
        [
            "user@example.com",
            "test.user@example.org",
            "admin@test.co.uk",
            "  user@example.com  ",
        ],
    )
    def test_validate_username_with_email_address(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        breach_service,
        mocker,
        email_username,
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.LoginForm(
            formdata=MultiDict({"username": email_username}),
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert str(form.username.errors.pop()) == (
            "Usernames are not the same as email addresses. "
            "Enter your username instead of your email address."
        )
        find_userid.assert_not_called()

    def test_validate_username_with_no_user(
        self, pyramid_config, pyramid_request, user_service, breach_service, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert str(form.username.errors.pop()) == "No user found with that username"
        find_userid.assert_called_once_with("my_username")

    @pytest.mark.parametrize(
        ("input_username", "expected_username"),
        [
            ("my_username", "my_username"),
            ("  my_username  ", "my_username"),
            ("my_username ", "my_username"),
            (" my_username", "my_username"),
            ("   my_username    ", "my_username"),
        ],
    )
    def test_validate_username_with_user(
        self,
        pyramid_request,
        user_service,
        breach_service,
        mocker,
        input_username,
        expected_username,
    ):
        # No password is checked here, so skip the argon2 hash.
        UserFactory.create(username="my_username")
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.LoginForm(
            formdata=MultiDict({"username": input_username}),
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert not form.username.errors
        find_userid.assert_called_once_with(expected_username)

    def test_validate_password_skips_when_field_has_errors(
        self, db_request, user_service, breach_service, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        check_password = mocker.spy(user_service, "check_password")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )
        form.password.errors = ["Password too long."]

        form.validate_password(form.password)

        # find_userid is called once by LoginForm.validate_password (after super()),
        # but not by PasswordMixin.validate_password (which returned early).
        find_userid.assert_called_once_with("my_username")
        # check_password is never called — the early return skipped it.
        check_password.assert_not_called()

    def test_validate_password_no_user(
        self, db_request, user_service, breach_service, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "password"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        form.validate_password(form.password)

        assert find_userid.call_args_list == [
            mocker.call("my_username"),
            mocker.call("my_username"),
        ]

    def test_validate_password_disabled_for_compromised_pw(
        self, db_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.patch.object(
            user_service,
            "is_disabled",
            autospec=True,
            return_value=(True, DisableReason.CompromisedPassword),
        )
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        with pytest.raises(wtforms.validators.ValidationError) as excinfo:
            form.validate_password(form.password)

        assert str(excinfo.value) == breach_service.failure_message
        assert find_userid.call_args_list == [
            mocker.call("my_username"),
            mocker.call("my_username"),
        ]
        is_disabled.assert_called_once_with(user.id)

    def test_validate_password_ok(
        self, db_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.spy(user_service, "is_disabled")
        check_password = mocker.spy(user_service, "check_password")
        breach_check_password = mocker.spy(breach_service, "check_password")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["bar"],
        )

        form.validate_password(form.password)

        assert find_userid.call_args_list == [
            mocker.call("my_username"),
            mocker.call("my_username"),
        ]
        is_disabled.assert_called_once_with(user.id)
        # check_password appends its own mechanism tag to the list it is given.
        check_password.assert_called_once_with(
            user.id, "pw", tags=["bar", "mechanism:check_password"]
        )
        breach_check_password.assert_called_once_with(
            "pw", tags=["method:auth", "auth_method:login_form"]
        )

    def test_validate_password_notok(
        self, db_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.spy(user_service, "is_disabled")
        check_password = mocker.spy(user_service, "check_password")
        record_event = mocker.spy(user, "record_event")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "wrong"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(form.password)

        find_userid.assert_called_once_with("my_username")
        is_disabled.assert_not_called()
        check_password.assert_called_once_with(user.id, "wrong", tags=None)
        record_event.assert_called_once_with(
            tag=EventTag.Account.LoginFailure,
            request=db_request,
            additional={"reason": "invalid_password"},
        )

    def test_validate_password_too_many_failed(
        self, db_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.spy(user_service, "is_disabled")
        check_password = mocker.patch.object(
            user_service,
            "check_password",
            autospec=True,
            side_effect=TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600)),
        )
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(form.password)

        find_userid.assert_called_once_with("my_username")
        is_disabled.assert_not_called()
        check_password.assert_called_once_with(user.id, "pw", tags=None)

    def test_password_breached(
        self, db_request, user_service, breach_service, user, mocker
    ):
        send_email = mocker.patch.object(
            forms, "send_password_compromised_email_hibp", autospec=True
        )
        disable_password = mocker.spy(user_service, "disable_password")
        mocker.patch.object(
            breach_service, "check_password", autospec=True, return_value=True
        )

        form = forms.LoginForm(
            MultiDict({"username": "my_username", "password": "pw"}),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.password.errors.pop() == breach_service.failure_message
        disable_password.assert_called_once_with(
            user.id, db_request, reason=DisableReason.CompromisedPassword
        )
        send_email.assert_called_once_with(db_request, user)
        assert user.disabled_for == DisableReason.CompromisedPassword

    def test_validate_password_ok_ip_banned(
        self, banned_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.spy(user_service, "is_disabled")
        check_password = mocker.spy(user_service, "check_password")
        breach_check_password = mocker.spy(breach_service, "check_password")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "pw"}),
            request=banned_request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["bar"],
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(form.password)

        find_userid.assert_not_called()
        is_disabled.assert_not_called()
        check_password.assert_not_called()
        breach_check_password.assert_not_called()

    def test_validate_password_notok_ip_banned(
        self, banned_request, user_service, breach_service, user, mocker
    ):
        find_userid = mocker.spy(user_service, "find_userid")
        is_disabled = mocker.spy(user_service, "is_disabled")
        check_password = mocker.spy(user_service, "check_password")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username", "password": "wrong"}),
            request=banned_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(form.password)

        find_userid.assert_not_called()
        is_disabled.assert_not_called()
        check_password.assert_not_called()


class TestRegistrationForm:
    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_validate(self, db_request, user_service, captcha_service, breach_service):
        form = forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict(
                {
                    "username": "myusername",
                    "new_password": "mysupersecurepassword1!",
                    "password_confirm": "mysupersecurepassword1!",
                    "email": "foo@bar.com",
                    "g_recaptcha_reponse": "",
                    "acceptable_use": "y",
                }
            ),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )

        assert form.user_service is user_service
        assert form.captcha_service is captcha_service
        assert form.validate(), str(form.errors)

    def test_acceptable_use_required_error(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        enabled_captcha_service,
        breach_service,
    ):
        """Registration is rejected when the acceptable use terms are unchecked."""
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.acceptable_use.errors.pop())
            == "You must agree to the Terms of Service and Acceptable Use Policy."
        )

    def test_acceptable_use_unchecked_value_error(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        """A submitted but falsy value is rejected, not only a missing one."""
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"acceptable_use": ""}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert form.acceptable_use.errors

    def test_password_confirm_required_error(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"password_confirm": ""}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        enabled_captcha_service,
        breach_service,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict(
                {"new_password": "password", "password_confirm": "mismatch"}
            ),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.password_confirm.errors.pop())
            == "Your passwords don't match. Try again."
        )

    def test_passwords_match_success(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                }
            ),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        form.validate()
        assert len(form.new_password.errors) == 0
        assert len(form.password_confirm.errors) == 0

    def test_email_required_error(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": ""}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert form.email.errors.pop() == "This field is required."

    @pytest.mark.parametrize("email", ["bad", "foo]bar@example.com", "</body></html>"])
    def test_invalid_email_error(
        self,
        pyramid_request,
        user_service,
        enabled_captcha_service,
        breach_service,
        email,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": email}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop()) == "The email address isn't valid. Try again."
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_exotic_email_success(
        self, db_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@n--tree.net"}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        form.validate()
        assert len(form.email.errors) == 0

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_email_exists_error(
        self, db_request, user_service, enabled_captcha_service, breach_service
    ):
        EmailFactory.create(email="foo@bar.com")
        form = forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_disposable_email_error(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bearsarefuzzy.com"}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        ("email", "prohibited_domain"),
        [
            ("foo@wutang.net", "wutang.net"),
            ("foo@clan.wutang.net", "wutang.net"),
            ("foo@one.two.wutang.net", "wutang.net"),
            ("foo@wUtAnG.net", "wutang.net"),
            ("foo@one.wutang.co.uk", "wutang.co.uk"),
        ],
    )
    def test_prohibited_email_error(
        self,
        db_request,
        user_service,
        enabled_captcha_service,
        breach_service,
        email,
        prohibited_domain,
    ):
        domain = ProhibitedEmailDomain(domain=prohibited_domain)
        db_request.db.add(domain)

        form = forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict({"email": email}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )

        assert not form.validate()
        assert form.email.errors
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )

    def _assert_reputation_metric(self, metrics, reason, *, prohibited):
        metrics.increment.assert_any_call(
            "warehouse.accounts.forms.validate_email_reputation",
            tags=[
                "result:invalid",
                f"reason:{reason}",
                f"prohibited:{'true' if prohibited else 'false'}",
            ],
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_email_error(
        self, remote_check_form, email_reputation_service, metrics, mocker
    ):
        check_email = mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@mailtowin.com")

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )
        # The full address is handed to the service: the /email/ endpoint
        # also catches throwaway addresses on otherwise legitimate domains.
        check_email.assert_called_once_with("foo@mailtowin.com")
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        ("email", "expected"),
        [
            pytest.param("foo@münchen.de", "foo@xn--mnchen-3ya.de", id="idn-domain"),
            # A non-ASCII local part has no ASCII form of the whole
            # address, but its domain still has to go out as punycode.
            pytest.param(
                "é@münchen.de", "é@xn--mnchen-3ya.de", id="unicode-local-part"
            ),
        ],
    )
    def test_remote_check_sends_the_ascii_form_of_an_idn_address(
        self,
        remote_check_form,
        email_reputation_service,
        mocker,
        email,
        expected,
    ):
        """
        The vendor answers on the punycode domain, so a Unicode submission
        has to be converted before it goes out; sending it raw errors the
        lookup, which fails open and skips the check entirely.
        """
        check_email = mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=EmailReputationResult(),
        )
        form = remote_check_form(email)

        assert form.validate()
        check_email.assert_called_once_with(expected)

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_domain_not_prohibited_when_flag_disabled(
        self, remote_check_form, db_request, email_reputation_service, metrics, mocker
    ):
        """
        The auto-prohibit write is gated behind the (default-off)
        AdminFlag; a disposable-domain verdict still blocks the attempt,
        but does not write to the blocklist while the flag is off.
        """
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@mailtowin.com")

        assert not form.validate()
        assert (
            db_request.db.scalars(
                select(ProhibitedEmailDomain).where(
                    ProhibitedEmailDomain.domain == "mailtowin.com"
                )
            ).one_or_none()
            is None
        )
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_email_is_added_to_prohibited_domains(
        self, remote_check_form, db_request, email_reputation_service, metrics, mocker
    ):
        db_request.db.get(
            AdminFlag, AdminFlagValue.AUTO_PROHIBIT_DISPOSABLE_DOMAINS.value
        ).enabled = True
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@mailtowin.com")

        assert not form.validate()

        prohibited = db_request.db.scalars(
            select(ProhibitedEmailDomain).where(
                ProhibitedEmailDomain.domain == "mailtowin.com"
            )
        ).one()
        assert prohibited.is_mx_record is False
        assert prohibited.prohibited_by is None
        assert prohibited.comment == (
            "Automatically prohibited: reported as a disposable email domain "
            "(provider: MailToWin)"
        )
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=True
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        ("email", "result_kwargs"),
        [
            # A public or relay domain, or flags an upstream payload
            # revision left unknown, must never escalate to a domain ban.
            pytest.param(
                "throwaway@gmail.com",
                {"public_domain": True, "relay_domain": False},
                id="public-domain",
            ),
            pytest.param(
                "throwaway@duck.com",
                {"public_domain": False, "relay_domain": True},
                id="relay-domain",
            ),
            pytest.param("throwaway@gmail.com", {}, id="unknown-flags"),
            # A private domain -- a university's, an employer's -- is
            # neither public nor relay, so those flags alone can't tell a
            # throwaway address on it apart from a disposable provider's
            # own domain. Only a named provider does.
            #
            # See: https://www.usercheck.com/docs/api/email-endpoint
            pytest.param(
                "spammer@mit.edu",
                {"public_domain": False, "relay_domain": False},
                id="private-domain-without-provider",
            ),
        ],
    )
    def test_remote_disposable_address_does_not_prohibit_domain(
        self,
        remote_check_form,
        db_request,
        email_reputation_service,
        metrics,
        mocker,
        email,
        result_kwargs,
    ):
        db_request.db.get(
            AdminFlag, AdminFlagValue.AUTO_PROHIBIT_DISPOSABLE_DOMAINS.value
        ).enabled = True
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=EmailReputationResult(disposable=True, **result_kwargs),
        )
        form = remote_check_form(email)

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use a disposable email address. Use a different email."
        )
        assert db_request.db.scalars(select(ProhibitedEmailDomain)).all() == []
        self._assert_reputation_metric(
            metrics, "disposable_address_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_email_existing_prohibition_not_duplicated(
        self, remote_check_form, db_request, email_reputation_service, metrics, mocker
    ):
        """
        A domain already prohibited with is_mx_record=True doesn't match the
        local database check for a direct use of that domain, so the remote
        check still runs. Recording its verdict must skip the insert instead
        of violating the unique constraint on domain.
        """
        db_request.db.get(
            AdminFlag, AdminFlagValue.AUTO_PROHIBIT_DISPOSABLE_DOMAINS.value
        ).enabled = True
        existing = ProhibitedEmailDomainFactory.create(
            domain="mailtowin.com", is_mx_record=True
        )
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@mailtowin.com")

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )
        # Flushing would raise IntegrityError if a duplicate row was added.
        db_request.db.flush()
        prohibited = db_request.db.scalars(
            select(ProhibitedEmailDomain).where(
                ProhibitedEmailDomain.domain == "mailtowin.com"
            )
        ).one()
        assert prohibited.id == existing.id
        assert prohibited.is_mx_record is True
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_subdomain_does_not_prohibit_parent_domain(
        self, remote_check_form, db_request, email_reputation_service, metrics, mocker
    ):
        """
        A disposable verdict on a subdomain-hosted address must not
        escalate to the shared parent apex, even with the flag on: other
        accounts may legitimately use that parent domain.
        """
        db_request.db.get(
            AdminFlag, AdminFlagValue.AUTO_PROHIBIT_DISPOSABLE_DOMAINS.value
        ).enabled = True
        check_email = mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@mail.one.mailtowin.com")

        assert not form.validate()
        check_email.assert_called_once_with("foo@mail.one.mailtowin.com")
        assert (
            db_request.db.scalars(
                select(ProhibitedEmailDomain).where(
                    ProhibitedEmailDomain.domain == "mailtowin.com"
                )
            ).one_or_none()
            is None
        )
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_disposable_email_with_empty_registrable_not_prohibited(
        self, remote_check_form, db_request, email_reputation_service, metrics, mocker
    ):
        """
        A host whose PSL-unknown TLD extracts to an empty registrable
        domain (e.g. a bare public suffix like "co.uk") must never be
        written: a domain='' row would match every address whose host has
        no registrable domain.
        """
        db_request.db.get(
            AdminFlag, AdminFlagValue.AUTO_PROHIBIT_DISPOSABLE_DOMAINS.value
        ).enabled = True
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=DISPOSABLE_DOMAIN_VERDICT,
        )
        form = remote_check_form("foo@co.uk")

        assert not form.validate()
        assert (
            db_request.db.scalars(
                select(ProhibitedEmailDomain).where(ProhibitedEmailDomain.domain == "")
            ).one_or_none()
            is None
        )
        self._assert_reputation_metric(
            metrics, "disposable_domain_reported", prohibited=False
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        "result_kwargs",
        [
            {},
            {"spam": True},
            {"public_domain": True},
            {"relay_domain": True},
            {"blocklisted": True},
            {"mx": False},
        ],
    )
    def test_remote_non_disposable_signals_do_not_block(
        self,
        remote_check_form,
        db_request,
        email_reputation_service,
        mocker,
        result_kwargs,
    ):
        # Anything other than "disposable" is recorded for observation only,
        # so we can measure it before deciding whether to gate on it.
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            return_value=EmailReputationResult(**result_kwargs),
        )
        form = remote_check_form("foo@example.com")

        assert form.validate(), str(form.errors)
        assert (
            db_request.db.scalars(
                select(ProhibitedEmailDomain).where(
                    ProhibitedEmailDomain.domain == "example.com"
                )
            ).one_or_none()
            is None
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        ("resets_in", "expected_error"),
        [
            (None, "Too many email addresses checked. Try again later."),
            (
                datetime.timedelta(minutes=10),
                "Too many email addresses checked. Try again in 10 minutes.",
            ),
        ],
    )
    def test_remote_check_rate_limited_blocks_the_attempt(
        self,
        remote_check_form,
        email_reputation_service,
        metrics,
        mocker,
        resets_in,
        expected_error,
    ):
        """
        A client that exhausted its own reputation-check budget is refused
        outright: failing open here would let it skip the check at will.
        """
        mocker.patch.object(
            email_reputation_service,
            "check_email",
            autospec=True,
            side_effect=TooManyEmailReputationChecks(resets_in=resets_in),
        )
        form = remote_check_form("foo@example.com")

        assert not form.validate()
        assert str(form.email.errors.pop()) == expected_error
        metrics.increment.assert_any_call(
            "warehouse.accounts.forms.validate_email_reputation",
            tags=["result:invalid", "reason:ratelimited"],
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_check_failure_fails_open(
        self, remote_check_form, email_reputation_service, mocker
    ):
        mocker.patch.object(
            email_reputation_service, "check_email", autospec=True, return_value=None
        )
        form = remote_check_form("foo@example.com")

        assert form.validate(), str(form.errors)

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_check_skipped_for_locally_prohibited_domain(
        self, remote_check_form, email_reputation_service, mocker
    ):
        # No need to spend a remote lookup on a domain we already know about.
        ProhibitedEmailDomainFactory.create(domain="wutang.net")
        check_email = mocker.patch.object(
            email_reputation_service, "check_email", autospec=True, return_value=None
        )
        form = remote_check_form("foo@wutang.net")

        assert not form.validate()
        check_email.assert_not_called()

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_check_skipped_for_email_already_in_use(
        self, remote_check_form, email_reputation_service, mocker
    ):
        check_email = mocker.patch.object(
            email_reputation_service, "check_email", autospec=True, return_value=None
        )
        EmailFactory.create(email="foo@example.com")
        form = remote_check_form("foo@example.com")

        assert not form.validate()
        check_email.assert_not_called()

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_remote_check_skipped_when_another_field_fails(
        self,
        remote_check_form,
        enabled_captcha_service,
        email_reputation_service,
        mocker,
    ):
        # The remote call is metered: a submission that already failed its
        # captcha (or any other field) must not spend the budget.
        check_email = mocker.patch.object(
            email_reputation_service, "check_email", autospec=True, return_value=None
        )
        form = remote_check_form("foo@example.com")
        # An enabled captcha with no response submitted.
        form.captcha_service = enabled_captcha_service

        assert not form.validate()
        check_email.assert_not_called()

    def test_recaptcha_disabled(
        self, pyramid_request, user_service, captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"g_recpatcha_response": ""}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        # there shouldn't be any errors for the recaptcha field if it's
        # disabled
        assert not form.g_recaptcha_response.errors

    def test_recaptcha_required_error(
        self, pyramid_request, user_service, enabled_captcha_service, breach_service
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"g_recaptcha_response": ""}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() == "Captcha error."

    def test_recaptcha_error(
        self,
        pyramid_request,
        user_service,
        enabled_captcha_service,
        breach_service,
        mocker,
    ):
        verify_response = mocker.patch.object(
            enabled_captcha_service,
            "verify_response",
            autospec=True,
            side_effect=recaptcha.RecaptchaError,
        )
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"g_recaptcha_response": "asd"}),
            user_service=user_service,
            captcha_service=enabled_captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() == "Captcha error."
        verify_response.assert_called_once_with("asd")

    def test_username_exists(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
    ):
        UserFactory.create(username="foo")
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"username": "foo"}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop())
            == "This username is already being used by another account. "
            "Choose a different username."
        )

    def test_username_prohibted(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
    ):
        ProhibitedUsernameFactory.create(name="foo")
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"username": "foo"}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop())
            == "This username is already being used by another account. "
            "Choose a different username."
        )

    @pytest.mark.parametrize("username", ["_foo", "bar_", "foo^bar", "boo\0far"])
    def test_username_is_valid(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
        username,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"username": username}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop()) == "The username is invalid. Usernames "
            "must be composed of letters, numbers, "
            "dots, hyphens and underscores. And must "
            "also start and finish with a letter or number. "
            "Choose a different username."
        )

    def test_password_strength(
        self, pyramid_request, user_service, captcha_service, breach_service
    ):
        cases = (
            ("foobar", False),
            ("somethingalittlebetter9", True),
            ("1aDeCent!1", True),
        )
        for pwd, valid in cases:
            form = forms.RegistrationForm(
                request=pyramid_request,
                formdata=MultiDict({"new_password": pwd, "password_confirm": pwd}),
                user_service=user_service,
                captcha_service=captcha_service,
                breach_service=breach_service,
            )
            form.validate()
            assert (len(form.new_password.errors) == 0) == valid

    def test_password_breached(
        self, pyramid_request, user_service, captcha_service, breach_service, mocker
    ):
        mocker.patch.object(
            breach_service, "check_password", autospec=True, return_value=True
        )
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"new_password": "password"}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.new_password.errors.pop() == breach_service.failure_message

    def test_name_too_long(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"full_name": "hello " * 50}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert (
            str(form.full_name.errors.pop())
            == "The name is too long. Choose a name with 100 characters or less."
        )

    def test_name_contains_null_bytes(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"full_name": "hello\0world"}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.full_name.errors.pop() == "Null bytes are not allowed."

    @pytest.mark.parametrize(
        "input_name",
        [
            "https://example.com",
            "hello http://example.com",
            "http://example.com goodbye",
        ],
    )
    def test_name_contains_url(
        self,
        pyramid_config,
        pyramid_request,
        user_service,
        captcha_service,
        breach_service,
        input_name,
    ):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"full_name": input_name}),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert (
            str(form.full_name.errors.pop())
            == "URLs are not allowed in the name field."
        )


class TestRequestPasswordResetForm:
    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        "form_input",
        [
            "username",
            "foo@bar.net",
        ],
    )
    def test_validate(self, user_service, form_input):
        form = forms.RequestPasswordResetForm(
            formdata=MultiDict({"username_or_email": form_input}),
            user_service=user_service,
        )
        assert form.validate()

    def test_no_password_field(self):
        form = forms.RequestPasswordResetForm()
        assert "password" not in form._fields

    @pytest.mark.parametrize("form_input", ["_username", "foo@bar@net", "foo@"])
    def test_validate_with_invalid_inputs(self, form_input):
        form = forms.RequestPasswordResetForm(
            formdata=MultiDict({"username_or_email": form_input})
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username_or_email(form.username_or_email)


class TestResetPasswordForm:
    def test_validate(self, breach_service):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            breach_service=breach_service,
        )

        assert form.validate(), str(form.errors)

    def test_password_confirm_required_error(self, breach_service):
        form = forms.ResetPasswordForm(
            formdata=MultiDict({"password_confirm": ""}),
            breach_service=breach_service,
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self, pyramid_config, breach_service):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "password",
                    "password_confirm": "mismatch",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            breach_service=breach_service,
        )

        assert not form.validate()
        assert (
            str(form.password_confirm.errors.pop())
            == "Your passwords don't match. Try again."
        )

    @pytest.mark.parametrize(
        ("password", "expected"),
        [("foobar", False), ("somethingalittlebetter9", True), ("1aDeCent!1", True)],
    )
    def test_password_strength(self, breach_service, password, expected):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": password,
                    "password_confirm": password,
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            breach_service=breach_service,
        )

        assert form.validate() == expected

    def test_password_breached(self, user_service, breach_service, mocker):
        mocker.patch.object(
            breach_service, "check_password", autospec=True, return_value=True
        )
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            user_service=user_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.new_password.errors.pop() == breach_service.failure_message


class TestTOTPAuthenticationForm:
    @pytest.mark.parametrize(
        "totp_value",
        [
            "123456",
            "1 2 3 4  5 6",
            "123 456",
        ],
    )
    def test_validate(self, db_request, user_service, mocker, totp_value):
        user = UserFactory.create()
        check_totp_value = mocker.patch.object(
            user_service, "check_totp_value", autospec=True, return_value=True
        )

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": totp_value}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )
        assert form.validate()
        # Spaces must be stripped so stored value matches future replay checks
        assert form.totp_value.data == "123456"
        check_totp_value.assert_called_once_with(user.id, b"123456")

    @pytest.mark.parametrize(
        ("totp_value", "expected_error"),
        [
            ("", "This field is required."),
            ("not_a_real_value", "TOTP code must be 6 digits."),
            ("1 2 3 4 5 6 7", "TOTP code must be 6 digits."),
        ],
    )
    def test_totp_secret_not_valid(
        self,
        pyramid_config,
        db_request,
        user_service,
        mocker,
        totp_value,
        expected_error,
    ):
        user = UserFactory.create()
        mocker.patch.object(
            user_service, "check_totp_value", autospec=True, return_value=True
        )

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": totp_value}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == expected_error

    def test_totp_secret_returns_false(
        self, pyramid_config, db_request, user_service, mocker
    ):
        # Without a TOTP secret, check_totp_value returns False.
        user = UserFactory.create(totp_secret=None)
        record_event = mocker.spy(user, "record_event")

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": "123456"}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == "Invalid TOTP code."
        record_event.assert_called_once_with(
            tag=EventTag.Account.LoginFailure,
            request=db_request,
            additional={"reason": "invalid_totp"},
        )

    @pytest.mark.parametrize(
        ("exception", "expected_error", "reason"),
        [
            (otp.InvalidTOTPError, "Invalid TOTP code.", "invalid_totp"),
            (otp.OutOfSyncTOTPError, "Invalid TOTP code.", "invalid_totp"),
        ],
    )
    def test_totp_secret_raises(
        self,
        pyramid_config,
        db_request,
        user_service,
        mocker,
        exception,
        expected_error,
        reason,
    ):
        user = UserFactory.create()
        record_event = mocker.spy(user, "record_event")
        mocker.patch.object(
            user_service, "check_totp_value", autospec=True, side_effect=exception
        )

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": "123456"}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == expected_error
        record_event.assert_called_once_with(
            tag=EventTag.Account.LoginFailure,
            request=db_request,
            additional={"reason": reason},
        )


class TestWebAuthnAuthenticationForm:
    def test_credential_valid(self, pyramid_request, user_service, mocker):
        challenge = mocker.sentinel.challenge
        origin = mocker.sentinel.origin
        rp_id = mocker.sentinel.rp_id
        verify_webauthn_assertion = mocker.patch.object(
            user_service,
            "verify_webauthn_assertion",
            autospec=True,
            return_value=("foo", 123456),
        )
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": json.dumps({})}),
            request=pyramid_request,
            user_id=mocker.sentinel.user_id,
            user_service=user_service,
            challenge=challenge,
            origin=origin,
            rp_id=rp_id,
        )

        assert form.challenge is challenge
        assert form.origin is origin
        assert form.rp_id is rp_id
        assert form.validate(), str(form.errors)
        assert form.validated_credential == ("foo", 123456)
        verify_webauthn_assertion.assert_called_once_with(
            mocker.sentinel.user_id,
            b"{}",
            challenge=challenge,
            origin=origin,
            rp_id=rp_id,
        )

    def test_credential_bad_payload(
        self, pyramid_config, pyramid_request, user_service, mocker
    ):
        verify_webauthn_assertion = mocker.spy(
            user_service, "verify_webauthn_assertion"
        )
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": "not valid json"}),
            request=pyramid_request,
            user_id=mocker.sentinel.user_id,
            user_service=user_service,
            challenge=mocker.sentinel.challenge,
            origin=mocker.sentinel.origin,
            rp_id=mocker.sentinel.rp_id,
        )
        assert not form.validate()
        assert (
            str(form.credential.errors.pop())
            == "Invalid WebAuthn assertion: Bad payload"
        )
        verify_webauthn_assertion.assert_not_called()

    def test_credential_invalid(self, db_request, user_service, mocker):
        user = UserFactory.create()
        record_event = mocker.spy(user, "record_event")
        mocker.patch.object(
            user_service,
            "verify_webauthn_assertion",
            autospec=True,
            side_effect=AuthenticationRejectedError("foo"),
        )
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": json.dumps({})}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
            challenge=mocker.sentinel.challenge,
            origin=mocker.sentinel.origin,
            rp_id=mocker.sentinel.rp_id,
        )
        assert not form.validate()
        assert form.credential.errors.pop() == "foo"
        record_event.assert_called_once_with(
            tag=EventTag.Account.LoginFailure,
            request=db_request,
            additional={"reason": "invalid_webauthn"},
        )


class TestReAuthenticateForm:
    def test_validate(self, pyramid_request, user_service, mocker):
        user = UserFactory.create(clear_pwd="mysupersecurepassword1!")
        check_password = mocker.spy(user_service, "check_password")

        form = forms.ReAuthenticateForm(
            formdata=MultiDict(
                {
                    "password": "mysupersecurepassword1!",
                    "next_route": "manage.projects",
                    "next_route_matchdict": "{}",
                    "next_route_query": "{}",
                }
            ),
            request=pyramid_request,
            user_id=user.id,
            user_service=user_service,
        )

        assert form.user_id == user.id
        assert form.user_service is user_service
        assert form.__params__ == [
            "password",
            "next_route",
            "next_route_matchdict",
            "next_route_query",
        ]
        assert isinstance(form.next_route, wtforms.StringField)
        assert isinstance(form.next_route_matchdict, wtforms.StringField)
        assert form.validate(), str(form.errors)
        check_password.assert_called_once_with(
            user.id, "mysupersecurepassword1!", tags=None
        )

    def test_validate_ignores_posted_username(
        self, pyramid_request, user_service, mocker
    ):
        user = UserFactory.create(clear_pwd="mysupersecurepassword1!")
        # Another account with the same password, which the form must not check.
        UserFactory.create(
            username="attacker-controlled", clear_pwd="mysupersecurepassword1!"
        )
        find_userid = mocker.spy(user_service, "find_userid")
        check_password = mocker.spy(user_service, "check_password")

        form = forms.ReAuthenticateForm(
            formdata=MultiDict(
                {
                    "username": "attacker-controlled",
                    "password": "mysupersecurepassword1!",
                    "next_route": "manage.projects",
                    "next_route_matchdict": "{}",
                    "next_route_query": "{}",
                }
            ),
            request=pyramid_request,
            user_id=user.id,
            user_service=user_service,
        )

        assert form.validate(), str(form.errors)
        check_password.assert_called_once_with(
            user.id, "mysupersecurepassword1!", tags=None
        )
        find_userid.assert_not_called()

    def test_requires_user_id(self, pyramid_request, user_service, mocker):
        # Without a user id, `validate_password` would skip the password check
        # altogether and validate any password, so building the form must fail.
        check_password = mocker.spy(user_service, "check_password")

        with pytest.raises(ValueError, match="user_id is required"):
            forms.ReAuthenticateForm(
                formdata=MultiDict(
                    {
                        "password": "totally-the-wrong-password",
                        "next_route": "manage.projects",
                        "next_route_matchdict": "{}",
                        "next_route_query": "{}",
                    }
                ),
                request=pyramid_request,
                user_id=None,
                user_service=user_service,
            )

        check_password.assert_not_called()

    def test_validate_password_with_field_errors(
        self, pyramid_request, user_service, mocker
    ):
        check_password = mocker.spy(user_service, "check_password")
        form = forms.ReAuthenticateForm(
            formdata=MultiDict({"password": "pw"}),
            request=pyramid_request,
            user_id=mocker.sentinel.user_id,
            user_service=user_service,
        )
        form.password.errors = ["This field is required."]

        form.validate_password(form.password)

        check_password.assert_not_called()

    def test_validate_password_too_many_failed(
        self, pyramid_request, user_service, mocker
    ):
        check_password = mocker.patch.object(
            user_service,
            "check_password",
            autospec=True,
            side_effect=TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600)),
        )
        form = forms.ReAuthenticateForm(
            formdata=MultiDict({"password": "pw"}),
            request=pyramid_request,
            user_id=mocker.sentinel.user_id,
            user_service=user_service,
        )

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(form.password)

        check_password.assert_called_once_with(mocker.sentinel.user_id, "pw", tags=None)


class TestRecoveryCodeForm:
    def test_validate(self, db_request, user_service, mocker):
        user = UserFactory.create()
        recovery_code = user_service.generate_recovery_codes(user.id)[0]
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": recovery_code}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )
        send_recovery_code_used_email = mocker.patch.object(
            forms, "send_recovery_code_used_email", autospec=True
        )

        assert form.request is db_request
        assert form.user_id is user.id
        assert form.user_service is user_service
        assert form.validate()
        send_recovery_code_used_email.assert_called_once_with(db_request, user)
        assert user_service.get_recovery_code(user.id, recovery_code).burned

    def test_missing_value(self, pyramid_request, user_service, mocker):
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": ""}),
            request=pyramid_request,
            user_id=mocker.sentinel.user_id,
            user_service=user_service,
        )
        assert not form.validate()
        assert form.recovery_code_value.errors.pop() == "This field is required."

    @pytest.mark.parametrize(
        ("exception", "expected_reason", "expected_error"),
        [
            (InvalidRecoveryCode, "invalid_recovery_code", "Invalid recovery code."),
            (NoRecoveryCodes, "invalid_recovery_code", "Invalid recovery code."),
            (
                BurnedRecoveryCode,
                "burned_recovery_code",
                "Recovery code has been previously used.",
            ),
        ],
    )
    def test_invalid_recovery_code(
        self,
        pyramid_config,
        db_request,
        user_service,
        mocker,
        exception,
        expected_reason,
        expected_error,
    ):
        user = UserFactory.create()
        record_event = mocker.spy(user, "record_event")
        mocker.patch.object(
            user_service, "check_recovery_code", autospec=True, side_effect=exception
        )
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": "deadbeef00001111"}),
            request=db_request,
            user_id=user.id,
            user_service=user_service,
        )

        assert not form.validate()
        assert str(form.recovery_code_value.errors.pop()) == expected_error
        record_event.assert_called_once_with(
            tag=EventTag.Account.LoginFailure,
            request=db_request,
            additional={"reason": expected_reason},
        )

    @pytest.mark.parametrize(
        ("input_string", "validates"),
        [
            # Valid: no spaces
            ("deadbeef00001111", True),
            # Valid: spaces are stripped before validation
            ("dead beef 0000 1111", True),
            ("deadbeef 00001111", True),
            (" deadbeef00001111 ", True),
            ("d e a d b e e f 0 0 0 0 1 1 1 1", True),
            # Invalid: wrong characters
            ("wu-tang", False),
            ("ghijklmnopqrstuv", False),
            # Invalid: wrong length (too many hex chars after spaces removed)
            ("deadbeef00001111 deadbeef11110000", False),
            # Invalid: too short
            ("deadbeef", False),
            # Invalid: exceeds passlib MAX_PASSWORD_SIZE
            ("a" * 5000, False),
        ],
    )
    def test_recovery_code_string_validation(
        self, db_request, user_service, mocker, input_string, validates
    ):
        user = UserFactory.create()
        mocker.patch.object(
            user_service, "check_recovery_code", autospec=True, return_value=True
        )
        form = forms.RecoveryCodeAuthenticationForm(
            request=db_request,
            formdata=MultiDict({"recovery_code_value": input_string}),
            user_id=user.id,
            user_service=user_service,
        )
        mocker.patch.object(forms, "send_recovery_code_used_email", autospec=True)

        assert form.validate() == validates
