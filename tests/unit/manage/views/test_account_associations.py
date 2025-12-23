# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPSeeOther
from webob.multidict import MultiDict

from tests.common.db.accounts import OAuthAccountAssociationFactory
from warehouse.events.tags import EventTag
from warehouse.manage.views import account_associations as views


class TestGitHubAssociationConnect:
    def test_initiates_oauth_flow(self, pyramid_request, oauth_provider_service):
        """Test that the connect view generates state and redirects to OAuth URL."""

        result = views.github_association_connect(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert (
            result.location
            == "http://localhost?code=mock_authorization_code&state="
            + pyramid_request.session["github_oauth_state"]
        )
        assert "github_oauth_state" in pyramid_request.session
        oauth_provider_service.generate_authorize_url.assert_called_once_with(
            pyramid_request.session["github_oauth_state"]
        )


class TestGitHubAssociationCallback:
    def test_invalid_state_csrf_error(self, pyramid_request):
        """Test that empty state token returns CSRF error."""
        pyramid_request.GET = MultiDict({"code": "test_code"})
        pyramid_request.route_path = lambda *args: "/manage/account/"

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "Invalid OAuth state - possible CSRF attack"
            in pyramid_request.session.peek_flash(queue="error")
        )

    def test_missing_state_csrf_error(self, pyramid_request):
        """Test that missing session state returns CSRF error."""
        # GET has a state but session doesn't have one stored
        pyramid_request.GET = MultiDict(
            {"state": "returned_state", "code": "test_code"}
        )
        pyramid_request.route_path = lambda *args: "/manage/account/"

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "Invalid OAuth state - possible CSRF attack"
            in pyramid_request.session.peek_flash(queue="error")
        )

    def test_oauth_error_from_github(self, pyramid_request):
        """Test handling of OAuth error response from GitHub."""
        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict(
            {
                "state": session_state,
                "error": "access_denied",
                "error_description": "User cancelled",
            }
        )
        pyramid_request.route_path = lambda *args: "/manage/account/"

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert "User cancelled" in pyramid_request.session.peek_flash(queue="error")[0]

    def test_missing_authorization_code(self, pyramid_request):
        """Test handling of missing authorization code."""
        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict({"state": session_state})
        pyramid_request.route_path = lambda *args: "/manage/account/"

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "No authorization code received from GitHub"
            in pyramid_request.session.peek_flash(queue="error")
        )

    def test_no_access_token_received(
        self, pyramid_request, oauth_provider_service, mocker
    ):
        """Test handling when token exchange returns no access token."""
        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict({"state": session_state, "code": "auth_code"})
        pyramid_request.route_path = lambda *args: "/manage/account/"

        # Mock exchange_code_for_token to return empty response (no access_token)
        mocker.patch.object(
            oauth_provider_service, "exchange_code_for_token", return_value={}
        )

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "No access token received"
            in pyramid_request.session.peek_flash(queue="error")[0]
        )

    def test_duplicate_association_value_error(
        self,
        pyramid_request,
        pyramid_user,
        oauth_provider_service,
        mocker,
    ):
        """Test handling when association already exists (ValueError)."""
        # Pre-create an association with known values
        OAuthAccountAssociationFactory.create(
            user=pyramid_user,
            service="github",
            external_user_id="12345",
            external_username="existinguser",
        )

        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict({"state": session_state, "code": "auth_code"})
        pyramid_request.route_path = lambda *args: "/manage/account/"

        # Mock get_user_info to return the same values as the existing association
        mocker.patch.object(
            oauth_provider_service,
            "get_user_info",
            return_value={"id": 12345, "login": "existinguser"},
        )

        # Attempt to create association - should fail as duplicate
        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "already associated" in pyramid_request.session.peek_flash(queue="error")[0]
        )

    def test_generic_exception_during_oauth(
        self, pyramid_request, oauth_provider_service, mocker
    ):
        """Test handling of unexpected exceptions during OAuth flow."""
        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict({"state": session_state, "code": "auth_code"})
        pyramid_request.route_path = lambda *args: "/manage/account/"
        # Mock OAuth service to raise an exception
        mocker.patch.object(
            oauth_provider_service,
            "exchange_code_for_token",
            side_effect=Exception("Network error"),
        )

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        assert (
            "unexpected error" in pyramid_request.session.peek_flash(queue="error")[0]
        )

    def test_successful_association(
        self,
        pyramid_request,
        pyramid_user,
        oauth_provider_service,
        user_service,
        mocker,
    ):
        """Test successful GitHub account association."""
        session_state = "valid_state"
        pyramid_request.session["github_oauth_state"] = session_state
        pyramid_request.GET = MultiDict({"state": session_state, "code": "auth_code"})
        pyramid_request.route_path = lambda *args: "/manage/account/"
        # Mock user's record_event method
        pyramid_user.record_event = mocker.Mock()
        # Mock the email sending function
        mock_send_email = mocker.patch.object(
            views, "send_account_association_added_email"
        )

        result = views.github_association_callback(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        # Verify association was created
        assert pyramid_user.account_associations[0].service == "github"
        # Verify event was recorded
        pyramid_user.record_event.assert_called_once()
        assert (
            pyramid_user.record_event.call_args[1]["tag"]
            == EventTag.Account.AccountAssociationAdd
        )
        # Verify email was sent
        mock_send_email.assert_called_once()
        # Verify success flash
        assert pyramid_request.session.peek_flash(queue="success")


class TestDeleteAccountAssociation:
    def test_successful_deletion(
        self, pyramid_request, pyramid_user, user_service, mocker
    ):
        """Test successful account association deletion."""
        mock_association = mocker.Mock()
        mock_association.id = "assoc-123"
        mock_association.service = "github"
        mock_association.external_username = "testuser"

        mock_form = mocker.Mock()
        mock_form.validate.return_value = True
        mock_form.association = mock_association

        pyramid_request.POST = MultiDict({"association_id": "assoc-123"})
        pyramid_request.route_path = lambda *args: "/manage/account/"
        pyramid_user.record_event = mocker.Mock()

        # Patch the form class and user_service method
        mocker.patch(
            "warehouse.manage.views.account_associations.DeleteAccountAssociationForm",
            return_value=mock_form,
        )
        mock_delete = mocker.patch.object(
            user_service, "delete_account_association", return_value=True
        )
        # Mock the email sending function
        mock_send_email = mocker.patch.object(
            views, "send_account_association_removed_email"
        )

        result = views.delete_account_association(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        mock_delete.assert_called_once_with("assoc-123")
        pyramid_user.record_event.assert_called_once()
        assert (
            pyramid_user.record_event.call_args[1]["tag"]
            == EventTag.Account.AccountAssociationRemove
        )
        # Verify email was sent
        mock_send_email.assert_called_once()
        assert pyramid_request.session.peek_flash(queue="success")

    def test_form_validation_failure(
        self, pyramid_request, pyramid_user, user_service, mocker
    ):
        """Test handling of form validation failure."""
        mock_form = mocker.Mock()
        mock_form.validate.return_value = False

        pyramid_request.POST = MultiDict({"association_id": "invalid"})
        pyramid_request.route_path = lambda *args: "/manage/account/"

        # Patch the form class
        mocker.patch(
            "warehouse.manage.views.account_associations.DeleteAccountAssociationForm",
            return_value=mock_form,
        )
        mock_delete = mocker.patch.object(
            user_service, "delete_account_association", return_value=True
        )

        result = views.delete_account_association(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage/account/"
        mock_delete.assert_not_called()
        assert (
            "Failed to remove account association"
            in pyramid_request.session.peek_flash(queue="error")
        )
