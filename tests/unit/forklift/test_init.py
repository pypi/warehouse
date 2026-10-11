# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse import forklift


@pytest.mark.parametrize("forklift_domain", [None, "upload.pypi.io"])
def test_includeme(forklift_domain, monkeypatch, mocker):
    settings = {}
    if forklift_domain:
        settings["forklift.domain"] = forklift_domain

    _help_url = mocker.sentinel.help_url
    monkeypatch.setattr(forklift, "_help_url", _help_url)

    _user_docs_url = mocker.sentinel.user_docs_url
    monkeypatch.setattr(forklift, "_user_docs_url", _user_docs_url)

    config = mocker.Mock(
        spec=[
            "get_settings",
            "include",
            "add_legacy_action_route",
            "add_template_view",
            "add_request_method",
            "add_route",
        ]
    )
    config.get_settings.return_value = settings

    forklift.includeme(config)

    config.include.assert_called_once_with(".action_routing")
    assert config.add_legacy_action_route.call_args_list == [
        mocker.call(
            "forklift.legacy.file_upload",
            "file_upload",
            auth_methods={"basic-auth", "macaroon"},
            domain=forklift_domain,
        ),
        mocker.call("forklift.legacy.submit", "submit", domain=forklift_domain),
        mocker.call(
            "forklift.legacy.submit_pkg_info", "submit_pkg_info", domain=forklift_domain
        ),
        mocker.call("forklift.legacy.doc_upload", "doc_upload", domain=forklift_domain),
    ]

    config.add_route.assert_called_once_with(
        "forklift.legacy.missing_trailing_slash", "/legacy", domain=forklift_domain
    )

    assert config.add_request_method.call_args_list == [
        mocker.call(_help_url, name="help_url"),
        mocker.call(_user_docs_url, name="user_docs_url"),
    ]
    if forklift_domain:
        assert config.add_template_view.call_args_list == [
            mocker.call(
                "forklift.index",
                "/",
                "upload.html",
                route_kw={"domain": forklift_domain},
                view_kw={"has_translations": True},
            ),
            mocker.call(
                "forklift.robots.txt",
                "/robots.txt",
                "forklift.robots.txt",
                route_kw={"domain": forklift_domain},
                view_kw={"has_translations": False},
            ),
            mocker.call(
                "forklift.legacy.invalid_request",
                "/legacy/",
                "upload.html",
                route_kw={"domain": "upload.pypi.io"},
                view_kw={"has_translations": True},
            ),
        ]
    else:
        config.add_template_view.assert_not_called()


def test_help_url(pyramid_request, mocker):
    warehouse_domain = mocker.sentinel.warehouse_domain
    result = mocker.sentinel.result
    pyramid_request.registry.settings["warehouse.domain"] = warehouse_domain
    route_url = mocker.patch.object(
        pyramid_request, "route_url", autospec=True, return_value=result
    )

    assert forklift._help_url(pyramid_request, _anchor="foo") == result
    route_url.assert_called_once_with("help", _host=warehouse_domain, _anchor="foo")


def test_user_docs_url(pyramid_request):
    docs_domain = "http://example.com"
    pyramid_request.registry.settings["userdocs.domain"] = docs_domain

    assert forklift._user_docs_url(pyramid_request, "/foo") == f"{docs_domain}/foo"
    assert (
        forklift._user_docs_url(pyramid_request, "/foo", anchor="bar")
        == f"{docs_domain}/foo#bar"
    )
