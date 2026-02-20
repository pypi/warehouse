# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import typing

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.oauth import IOAuthProviderService, generate_state_token
from warehouse.authnz import Permissions
from warehouse.email import (
    send_account_association_added_email,
    send_account_association_removed_email,
)
from warehouse.events.tags import EventTag
from warehouse.manage.forms import DeleteAccountAssociationForm

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@view_config(
    route_name="manage.account.associations.github.connect",
    request_method="GET",
    permission=Permissions.AccountManage,
    uses_session=True,
    require_csrf=False,
    require_methods=False,
    has_translations=True,
)
def github_association_connect(request: Request) -> HTTPSeeOther:
    """
    Initiate GitHub OAuth flow for account association.
    """
    # Generate state token for CSRF protection
    state = generate_state_token()
    request.session["github_oauth_state"] = state

    # Get OAuth client from registry
    oauth_client = request.find_service(IOAuthProviderService, name="github")
    auth_url = oauth_client.generate_authorize_url(state)

    return HTTPSeeOther(location=auth_url)


@view_config(
    route_name="manage.account.associations.github.callback",
    request_method="GET",
    permission=Permissions.AccountManage,
    uses_session=True,
    require_csrf=False,
    require_methods=False,
    has_translations=True,
)
def github_association_callback(request: Request) -> HTTPSeeOther:
    """
    Handle GitHub OAuth callback for account association.
    """
    # Verify state token to prevent CSRF
    returned_state = request.GET.get("state")
    session_state = request.session.pop("github_oauth_state", None)

    if not returned_state or returned_state != session_state:
        request.session.flash(
            request._("Invalid OAuth state - possible CSRF attack"), queue="error"
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Check for OAuth error
    error = request.GET.get("error")
    if error:
        error_description = request.GET.get("error_description", error)
        request.session.flash(
            request._(
                "GitHub OAuth failed: ${error}", mapping={"error": error_description}
            ),
            queue="error",
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Exchange code for access token
    code = request.GET.get("code")
    if not code:
        request.session.flash(
            request._("No authorization code received from GitHub"), queue="error"
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Get OAuth client from registry
    oauth_client = request.find_service(IOAuthProviderService, name="github")
    user_service = request.find_service(IUserService)

    try:
        # Exchange authorization code for access token
        token_data = oauth_client.exchange_code_for_token(code)
        access_token = token_data.get("access_token")

        if not access_token:
            raise ValueError("No access token received")

        # Get user info from GitHub
        github_user = oauth_client.get_user_info(access_token)
        external_user_id = str(github_user["id"])
        external_username = github_user["login"]

        # Create account association (we don't store OAuth tokens - identity only)
        user_service.add_account_association(
            user_id=str(request.user.id),
            service="github",
            external_user_id=external_user_id,
            external_username=external_username,
        )

        # Record event
        request.user.record_event(
            tag=EventTag.Account.AccountAssociationAdd,
            request=request,
            additional={
                "service": "github",
                "external_username": external_username,
            },
        )

        # Send notification email
        send_account_association_added_email(
            request,
            request.user,
            service="GitHub",
            external_username=external_username,
        )

        request.session.flash(
            request._(
                "Successfully connected GitHub account @${username}",
                mapping={"username": external_username},
            ),
            queue="success",
        )

    except ValueError as exc:
        request.session.flash(
            request._(
                "Failed to connect GitHub account: ${error}",
                mapping={"error": str(exc)},
            ),
            queue="error",
        )
    except Exception as exc:
        # Log the error but show generic message to user
        request.log.error(f"GitHub OAuth error: {exc}")
        request.session.flash(
            request._(
                "An unexpected error occurred while connecting your GitHub account"
            ),
            queue="error",
        )

    return HTTPSeeOther(location=request.route_path("manage.account"))


@view_config(
    route_name="manage.account.associations.gitlab.connect",
    request_method="GET",
    permission=Permissions.AccountManage,
    uses_session=True,
    require_csrf=False,
    require_methods=False,
    has_translations=True,
)
def gitlab_association_connect(request: Request) -> HTTPSeeOther | HTTPNotFound:
    """
    Initiate GitLab OAuth flow for account association.
    """
    if not request.registry.settings.get("gitlab.oauth.backend"):
        return HTTPNotFound()

    # Generate state token for CSRF protection
    state = generate_state_token()
    request.session["gitlab_oauth_state"] = state

    # Get OAuth client from registry
    oauth_client = request.find_service(IOAuthProviderService, name="gitlab")
    auth_url = oauth_client.generate_authorize_url(state)

    return HTTPSeeOther(location=auth_url)


@view_config(
    route_name="manage.account.associations.gitlab.callback",
    request_method="GET",
    permission=Permissions.AccountManage,
    uses_session=True,
    require_csrf=False,
    require_methods=False,
    has_translations=True,
)
def gitlab_association_callback(request: Request) -> HTTPSeeOther | HTTPNotFound:
    """
    Handle GitLab OAuth callback for account association.
    """
    if not request.registry.settings.get("gitlab.oauth.backend"):
        return HTTPNotFound()

    # Verify state token to prevent CSRF
    returned_state = request.GET.get("state")
    session_state = request.session.pop("gitlab_oauth_state", None)

    if not returned_state or returned_state != session_state:
        request.session.flash(
            request._("Invalid OAuth state - possible CSRF attack"), queue="error"
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Check for OAuth error
    error = request.GET.get("error")
    if error:
        error_description = request.GET.get("error_description", error)
        request.session.flash(
            request._(
                "GitLab OAuth failed: ${error}", mapping={"error": error_description}
            ),
            queue="error",
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Exchange code for access token
    code = request.GET.get("code")
    if not code:
        request.session.flash(
            request._("No authorization code received from GitLab"), queue="error"
        )
        return HTTPSeeOther(location=request.route_path("manage.account"))

    # Get OAuth client from registry
    oauth_client = request.find_service(IOAuthProviderService, name="gitlab")
    user_service = request.find_service(IUserService)

    try:
        # Exchange authorization code for access token
        token_data = oauth_client.exchange_code_for_token(code)
        access_token = token_data.get("access_token")

        if not access_token:
            raise ValueError("No access token received")

        # Get user info from GitLab
        gitlab_user = oauth_client.get_user_info(access_token)
        external_user_id = str(gitlab_user["id"])
        # GitLab uses 'username' instead of GitHub's 'login'
        external_username = gitlab_user["username"]

        # Create account association (we don't store OAuth tokens - identity only)
        user_service.add_account_association(
            user_id=str(request.user.id),
            service="gitlab",
            external_user_id=external_user_id,
            external_username=external_username,
        )

        # Record event
        request.user.record_event(
            tag=EventTag.Account.AccountAssociationAdd,
            request=request,
            additional={
                "service": "gitlab",
                "external_username": external_username,
            },
        )

        # Send notification email
        send_account_association_added_email(
            request,
            request.user,
            service="GitLab",
            external_username=external_username,
        )

        request.session.flash(
            request._(
                "Successfully connected GitLab account @${username}",
                mapping={"username": external_username},
            ),
            queue="success",
        )

    except ValueError as exc:
        request.session.flash(
            request._(
                "Failed to connect GitLab account: ${error}",
                mapping={"error": str(exc)},
            ),
            queue="error",
        )
    except Exception as exc:
        # Log the error but show generic message to user
        request.log.error(f"GitLab OAuth error: {exc}")
        request.session.flash(
            request._(
                "An unexpected error occurred while connecting your GitLab account"
            ),
            queue="error",
        )

    return HTTPSeeOther(location=request.route_path("manage.account"))


@view_config(
    route_name="manage.account.associations.delete",
    request_method="POST",
    request_param=DeleteAccountAssociationForm.__params__,
    permission=Permissions.AccountManage,
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
    require_reauth=True,
)
def delete_account_association(request: Request) -> HTTPSeeOther:
    """
    Delete an account association.
    """
    user_service = request.find_service(IUserService)

    form = DeleteAccountAssociationForm(
        request.POST,
        user_service=user_service,
        user_id=request.user.id,
    )

    if form.validate():
        association = form.association

        # Currently we only support OAuth associations
        # Prepare event data with OAuth-specific fields
        event_data = {
            "service": association.service,
            "external_username": association.external_username,
        }
        flash_data = {
            "service": association.service.capitalize(),
            "username": association.external_username,
        }

        # Record event before deletion
        request.user.record_event(
            tag=EventTag.Account.AccountAssociationRemove,
            request=request,
            additional=event_data,
        )

        # Send notification email before deletion
        send_account_association_removed_email(
            request,
            request.user,
            service=association.service.capitalize(),
            external_username=association.external_username,
        )

        # Delete the association
        user_service.delete_account_association(str(association.id))

        request.session.flash(
            request._(
                "Removed ${service} account @${username}",
                mapping=flash_data,
            ),
            queue="success",
        )
    else:
        request.session.flash(
            request._("Failed to remove account association"), queue="error"
        )

    return HTTPSeeOther(location=request.route_path("manage.account"))
