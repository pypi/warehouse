# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from ...common.db.accounts import UserFactory


@pytest.mark.parametrize("is_superuser", [True, False])
def test_api_keys_page_is_admin_only(webtest, login_user, is_superuser):
    user = UserFactory.create(
        is_superuser=is_superuser,
        with_verified_primary_email=True,
        with_terms_of_service_agreement=True,
        clear_pwd="password",
    )
    login_user(user)

    status = HTTPStatus.OK if is_superuser else HTTPStatus.FORBIDDEN
    webtest.get("/manage/account/api-keys/", status=status)


def test_create_and_use_api_key(webtest, login_user):
    user = UserFactory.create(
        is_superuser=True,
        with_verified_primary_email=True,
        with_terms_of_service_agreement=True,
        clear_pwd="password",
    )
    login_user(user)

    page = webtest.get("/manage/account/api-keys/", status=HTTPStatus.OK)
    form = page.forms["create-api-key-form"]
    form["name"] = "echo"
    form["scopes"] = ["test:echo"]
    created = form.submit(status=HTTPStatus.OK)
    raw_key = created.html.select_one("#provisioned-key code.code-block").text

    resp = webtest.get(
        "/danger-api/echo",
        headers={
            "Authorization": f"Bearer {raw_key}",
            "Accept": "application/vnd.pypi.api-v0-danger+json",
        },
        status=HTTPStatus.OK,
    )
    assert resp.json == {"username": user.username}
