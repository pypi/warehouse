# SPDX-License-Identifier: Apache-2.0

import uuid

import pretend
import pytest

from warehouse.admin.views import macaroons as views
from warehouse.macaroons import caveats

from ....common.db.accounts import UserFactory


@pytest.fixture
def raw_token():
    """
    A valid macaroon token string, without a database object.
    Intentionally split across lines to prevent false-positive detection by
    scanners, as it's only used for testing.
    """
    return (
        "py"
        "pi-AgEIcHlwaS5vcmcCJGQ0ZDhhNzA2LTUxYTEtNDg0NC1hNDlmLTEyZDRiYzNkYjZmOQAABi"
        "D6hJOpYl9jFI4jBPvA8gvV1mSu1Ic3xMHmxA4CSA2w_g"
    )


class TestMacaroonDecodeToken:
    def test_get(self, db_request):
        db_request.method = "GET"
        result = views.macaroon_decode_token(db_request)

        assert result == {}

    def test_post_no_token(self, db_request):
        db_request.method = "POST"

        with pytest.raises(views.HTTPBadRequest) as excinfo:
            views.macaroon_decode_token(db_request)
        assert excinfo.value.message == "No token provided."

    def test_post_invalid_token(self, db_request):
        db_request.method = "POST"
        db_request.POST = {"token": "invalid"}

        with pytest.raises(views.HTTPBadRequest) as excinfo:
            views.macaroon_decode_token(db_request)
        assert excinfo.value.message == (
            "The token cannot be deserialized: InvalidMacaroonError('malformed "
            "or nonexistent macaroon')"
        )

    def test_post_token_found(self, db_request, macaroon_service):
        user = UserFactory.create()
        db_request.user = user
        token, macaroon = macaroon_service.create_macaroon(
            location="fake location",
            description="real description",
            scopes=[caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )
        db_request.method = "POST"
        db_request.POST = {"token": token}

        result = views.macaroon_decode_token(db_request)

        assert result["macaroon"].location == "fake location"
        assert result["db_record"].description == "real description"

    def test_post_token_not_found(self, db_request, macaroon_service, raw_token):
        db_request.method = "POST"
        db_request.POST = {"token": raw_token}

        result = views.macaroon_decode_token(db_request)

        # Can't compare the macaroon directly, because it will have a different
        # identifier. https://github.com/ecordell/pymacaroons/issues/62
        assert result["macaroon"].location == "pypi.org"
        assert result["db_record"] is None


class TestMacaroonDetail:
    def test_no_macaroon_raises_404(self, db_request):
        db_request.matchdict["macaroon_id"] = uuid.uuid4()

        with pytest.raises(views.HTTPNotFound):
            views.macaroon_detail(db_request)

    def test_macaroon_exists(self, db_request, macaroon_service):
        user = UserFactory.create()
        _, macaroon = macaroon_service.create_macaroon(
            location="test",
            description="test",
            scopes=[caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )
        db_request.matchdict["macaroon_id"] = macaroon.id

        result = views.macaroon_detail(db_request)

        assert result["macaroon"] == macaroon


class TestMacaroonDelete:
    def test_no_macaroon_raises_404(self, db_request, macaroon_service):
        db_request.matchdict["macaroon_id"] = str(uuid.uuid4())

        with pytest.raises(views.HTTPNotFound):
            views.macaroon_delete(db_request)

    def test_delete_succeeds_and_redirects(self, db_request, macaroon_service):
        user = UserFactory.create()
        db_request.user = user
        _, macaroon = macaroon_service.create_macaroon(
            location="test",
            description="test",
            scopes=[caveats.RequestUser(user_id=str(user.id))],
            user_id=user.id,
        )
        macaroon_id = str(macaroon.id)
        db_request.matchdict["macaroon_id"] = macaroon_id
        db_request.route_url = pretend.call_recorder(
            lambda *a, **kw: "/admin/macaroons/decode"
        )

        result = views.macaroon_delete(db_request)

        assert result.status_code == views.HTTPSeeOther.code
        assert result.location == "/admin/macaroons/decode"
        assert macaroon_service.find_macaroon(macaroon_id) is None
