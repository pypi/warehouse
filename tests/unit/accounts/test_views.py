import pytest

from unittest import mock
from pretend import stub

from django.conf import settings
from django.core.urlresolvers import reverse
from django.shortcuts import resolve_url
from django.test.utils import override_settings

from warehouse.accounts.adapters import Email
from warehouse.accounts.forms import SignupForm
from warehouse.accounts.views import (
        LoginView, SignupView, AccountSettingsView, DeleteAccountEmailView,
        SetPrimaryEmailView
    )


@pytest.mark.parametrize(("url", "expected"), [
    ("/foo/", "/foo/"),
    ("http://bad.example.com/foo/", "/account/profile/"),
    ("http://testserver/bar/", "http://testserver/bar/"),
])
@override_settings(LOGIN_REDIRECT_URL="/account/profile/")
def test_login_get_next_url_via_get(url, expected, rf):
    view = LoginView()
    req = rf.get("/account/login/?next=" + url)
    assert view._get_next_url(req) == expected


@pytest.mark.parametrize(("url", "expected"), [
    ("/foo/", "/foo/"),
    ("http://bad.example.com/foo/", "/account/profile/"),
    ("http://testserver/bar/", "http://testserver/bar/"),
])
@override_settings(LOGIN_REDIRECT_URL="/account/profile/")
def test_login_get_next_url_via_post(url, expected, rf):
    view = LoginView()
    req = rf.get("/account/login/", {"next": url})
    assert view._get_next_url(req) == expected


def test_login_already_logged_in(rf):
    view = LoginView.as_view()
    req = rf.get("/account/login/?next=/foo/")
    req.user = stub(is_authenticated=lambda: True)
    resp = view(req)

    assert resp.status_code == 303
    assert resp["Location"] == "/foo/"

    req = rf.post("/account/login/", {"next": "/foo/"})
    req.user = stub(is_authenticated=lambda: True)
    resp = view(req)

    assert resp.status_code == 303
    assert resp["Location"] == "/foo/"


def test_login_flow(rf):
    user = stub(is_authenticated=lambda: False, is_active=True)
    authenticator = mock.Mock(return_value=user)
    login = mock.Mock()
    view = LoginView.as_view(authenticator=authenticator, login=login)

    # Verify that we can GET the login url
    request = rf.get(reverse("accounts.login"))
    request.user = user
    response = view(request)

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None

    # Attempt to login the user and verify it worked
    data = {"username": "testuser", "password": "test password"}
    request = rf.post(reverse("accounts.login"), data)
    request.user = user
    response = view(request)

    assert response.status_code == 303
    assert "Location" in response
    assert response["Location"] == resolve_url(settings.LOGIN_REDIRECT_URL)

    assert authenticator.call_count == 1
    assert authenticator.call_args == (tuple(), data)

    assert login.call_count == 1
    assert login.call_args == ((request, user), {})


def test_login_invalid_form(rf):
    user = stub(is_authenticated=lambda: False)
    authenticator = mock.Mock(return_value=None)
    login = mock.Mock()
    view = LoginView.as_view(authenticator=authenticator, login=login)

    # Attempt to login with invalid form data
    data = {"username": "testuser"}
    request = rf.post(reverse("accounts.login"), data)
    request.user = user
    response = view(request)

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None
    assert response.context_data["form"].errors == {
                "password": ["This field is required."],
            }


def test_login_invalid_user(rf):
    user = stub(is_authenticated=lambda: False)
    authenticator = mock.Mock(return_value=None)
    login = mock.Mock()
    view = LoginView.as_view(authenticator=authenticator, login=login)

    # Attempt to login with an invalid user
    data = {"username": "testuser", "password": "test password"}
    request = rf.post(reverse("accounts.login"), data)
    request.user = user
    response = view(request)

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None
    assert response.context_data["form"].errors == {
                "__all__": ["Invalid username or password"],
            }


def test_login_inactive_user(rf):
    user = stub(is_authenticated=lambda: True, is_active=False)
    authenticator = mock.Mock(return_value=user)
    login = mock.Mock()
    view = LoginView.as_view(authenticator=authenticator, login=login)

    # Attempt to login with an inactive user
    data = {"username": "testuser", "password": "test password"}
    request = rf.post(reverse("accounts.login"), data)
    request.user = stub(is_authenticated=lambda: False)
    response = view(request)

    assert authenticator.call_count == 1
    assert authenticator.call_args == (tuple(), data)
    assert login.call_count == 0

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None
    assert response.context_data["form"].errors == {
                "__all__": [
                    ("This account is inactive or has been locked by "
                    "an administrator.")
                ],
            }


def test_signup_flow(rf):
    class TestSignupForm(SignupForm):
        model = stub(api=stub(username_exists=lambda x: False))

    creator = mock.Mock()
    view = SignupView.as_view(creator=creator, form_class=TestSignupForm)

    # Verify that we can GET the signup url
    request = rf.get(reverse("accounts.signup"))
    response = view(request)

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None
    assert isinstance(response.context_data["form"], SignupForm)

    # Attempt to create the user and verify it worked
    data = {
                "username": "testuser",
                "email": "test@example.com",
                "password": "test password",
                "confirm_password": "test password",
            }
    request = rf.post(reverse("accounts.signup"), data)
    response = view(request)

    assert response.status_code == 303
    assert "Location" in response
    assert response["Location"] == resolve_url(settings.LOGIN_REDIRECT_URL)

    assert creator.call_count == 1
    assert creator.call_args == (tuple(), {
                                                "username": "testuser",
                                                "email": "test@example.com",
                                                "password": "test password",
                                            })


@pytest.mark.parametrize(("data", "errors"), [
    (
        {
            "email": "test@example.com",
            "password": "test password",
            "confirm_password": "test password",
        },
        {"username": ["This field is required."]},
    ),
])
def test_signup_invalid(data, errors, rf):
    class TestSignupForm(SignupForm):
        model = stub(api=stub(username_exists=lambda x: False))

    creator = mock.Mock()
    view = SignupView.as_view(creator=creator, form_class=TestSignupForm)

    request = rf.post(reverse("accounts.signup"), data)
    response = view(request)

    assert response.status_code == 200
    assert response.context_data.keys() == set(["next", "form"])
    assert response.context_data["next"] is None
    assert isinstance(response.context_data["form"], SignupForm)
    assert response.context_data["form"].errors == errors


def test_signup_ensure_next(rf):
    class TestSignupForm(SignupForm):
        model = stub(api=stub(username_exists=lambda x: False))

    view = SignupView.as_view(
                creator=lambda *args, **kwargs: None,
                form_class=TestSignupForm,
            )

    # Test that next is properly added to the context for a GET
    request = rf.get(reverse("accounts.signup"), {"next": "/test/next/"})
    response = view(request)
    assert response.context_data["next"] == "/test/next/"

    # Test that next is properly added to the context for an invalid POST
    request = rf.post(reverse("accounts.signup"), {"next": "/test/next/"})
    response = view(request)
    assert response.context_data["next"] == "/test/next/"

    # Test that when given valid data POST redirects to next
    request = rf.post(reverse("accounts.signup"), {
                    "next": "/test/next/",
                    "username": "testuser",
                    "email": "test@example.com",
                    "password": "test password",
                    "confirm_password": "test password",
                })
    response = view(request)
    assert response["Location"] == "/test/next/"


def test_account_settings_anonymous_redirect(rf):
    get_emails = lambda x: pytest.fail("get_emails shouldn't have been called")
    view = AccountSettingsView.as_view(get_emails=get_emails)

    request = rf.get(reverse("accounts.settings"))
    request.user = stub(is_authenticated=lambda: False)
    response = view(request)

    assert response.status_code == 302
    assert response["Location"] == (
        reverse("accounts.login") + "?next=" + reverse("accounts.settings"))


def test_account_settings_ensure_email(rf):
    emails = [
        Email("testuser", "test@example.com", True, True),
        Email("testuser", "test2@example.com", False, True),
        Email("testuser", "test3@example.com", False, True),
    ]

    get_emails = mock.Mock(return_value=emails)
    view = AccountSettingsView.as_view(get_emails=get_emails)

    request = rf.get(reverse("accounts.settings"))
    request.user = stub(is_authenticated=lambda: True, username="testuser")
    response = view(request)

    assert response.status_code == 200
    assert response.context_data["emails"] == emails


def test_account_settings_delete_email(rf):
    delete_email = mock.Mock()
    view = DeleteAccountEmailView.as_view(delete_email=delete_email)

    request = rf.post(reverse("accounts.delete-email",
                                    kwargs={"email": "test@example.com"}))
    request.META["HTTP_REFERER"] = "http://testserver/"
    request.user = stub(is_authenticated=lambda: True, username="testuser")
    response = view(request, "test@example.com")

    assert response.status_code == 303
    assert response["Location"] == "http://testserver/"

    assert delete_email.call_count == 1
    assert delete_email.call_args == (("testuser", "test@example.com"), {})


def test_account_settings_delete_email_invalid_referer(rf):
    delete_email = mock.Mock()
    view = DeleteAccountEmailView.as_view(delete_email=delete_email)

    request = rf.post(reverse("accounts.delete-email",
                                    kwargs={"email": "test@example.com"}))
    request.META["HTTP_REFERER"] = "http://evil.example.com/"
    request.user = stub(is_authenticated=lambda: True, username="testuser")
    response = view(request, "test@example.com")

    assert response.status_code == 303
    assert response["Location"] == reverse("accounts.settings")

    assert delete_email.call_count == 1
    assert delete_email.call_args == (("testuser", "test@example.com"), {})


def test_account_settings_set_primary_email(rf):
    set_primary = mock.Mock()
    view = SetPrimaryEmailView.as_view(set_primary_email=set_primary)

    request = rf.post(reverse("accounts.set-primary-email",
                                    kwargs={"email": "test@example.com"}))
    request.META["HTTP_REFERER"] = "http://testserver/"
    request.user = stub(is_authenticated=lambda: True, username="testuser")
    response = view(request, "test@example.com")

    assert response.status_code == 303
    assert response["Location"] == "http://testserver/"

    assert set_primary.call_count == 1
    assert set_primary.call_args == (("testuser", "test@example.com"), {})


def test_account_settings_set_primary_email_invalid_referer(rf):
    set_primary = mock.Mock()
    view = SetPrimaryEmailView.as_view(set_primary_email=set_primary)

    request = rf.post(reverse("accounts.set-primary-email",
                                    kwargs={"email": "test@example.com"}))
    request.META["HTTP_REFERER"] = "http://evil.example.com/"
    request.user = stub(is_authenticated=lambda: True, username="testuser")
    response = view(request, "test@example.com")

    assert response.status_code == 303
    assert response["Location"] == reverse("accounts.settings")

    assert set_primary.call_count == 1
    assert set_primary.call_args == (("testuser", "test@example.com"), {})
