# SPDX-License-Identifier: Apache-2.0


import pytest

from pyramid.httpexceptions import HTTPNotFound
from webob.multidict import MultiDict

from warehouse.admin.views import api_keys as views
from warehouse.events.tags import EventTag
from warehouse.utils import now

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory


@pytest.fixture
def revoke_request(db_request, mocker):
    db_request.method = "POST"
    db_request.user = UserFactory.create(username="admin")
    db_request.POST = MultiDict()
    mocker.patch.object(
        db_request,
        "route_path",
        autospec=True,
        side_effect=lambda name, **kw: f"/{name}/{kw['username']}/",
    )
    mocker.spy(db_request.session, "flash")
    return db_request


@pytest.mark.parametrize(
    ("post", "notify", "reason"),
    [
        pytest.param({}, False, None, id="quiet"),
        pytest.param(
            {"notify": "on", "reason": " Leaked in a CI log "},
            True,
            "Leaked in a CI log",
            id="notify with reason",
        ),
    ],
)
def test_api_key_revoke(revoke_request, mocker, post, notify, reason):
    api_key = ApiKeyFactory.create(name="ci", user__username="owner")
    record_event = mocker.spy(api_key.user, "record_event")
    send_email = mocker.patch.object(
        views, "send_api_key_compromised_email", autospec=True
    )
    revoke_request.matchdict = {"api_key_id": str(api_key.id)}
    revoke_request.POST = MultiDict(post)

    result = views.api_key_revoke(revoke_request)

    assert result.headers["Location"] == "/admin.user.detail/owner/"
    assert api_key.revoked is not None
    additional = {
        "name": "ci",
        "api_key_id": str(api_key.id),
        "revoked_by": "admin",
        "redact_ip": True,
    }
    if reason:
        additional["reason"] = reason
    record_event.assert_called_once_with(
        tag=EventTag.Account.APIKeyRevoked,
        request=revoke_request,
        additional=additional,
    )
    if notify:
        send_email.assert_called_once_with(
            revoke_request,
            api_key.user,
            name="ci",
            admin_initiated=True,
            reason=reason,
        )
    else:
        send_email.assert_not_called()
    revoke_request.session.flash.assert_called_once_with(
        "Maintainer API key 'ci' revoked", queue="success"
    )


def test_api_key_revoke_already_revoked(revoke_request, mocker):
    api_key = ApiKeyFactory.create(name="ci", revoked=now())
    record_event = mocker.spy(api_key.user, "record_event")
    revoke_request.matchdict = {"api_key_id": str(api_key.id)}

    views.api_key_revoke(revoke_request)

    record_event.assert_not_called()
    revoke_request.session.flash.assert_called_once_with(
        "Maintainer API key 'ci' was already revoked", queue="error"
    )


@pytest.mark.parametrize(
    "api_key_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"]
)
def test_api_key_revoke_not_found(revoke_request, api_key_id):
    revoke_request.matchdict = {"api_key_id": api_key_id}

    assert isinstance(views.api_key_revoke(revoke_request), HTTPNotFound)
