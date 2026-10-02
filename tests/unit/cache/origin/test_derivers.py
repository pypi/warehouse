# SPDX-License-Identifier: Apache-2.0

import types

from warehouse.cache.origin import derivers


def test_no_renderer(mocker):
    view = mocker.sentinel.view
    info = types.SimpleNamespace(options={})

    assert derivers.html_cache_deriver(view, info) == view


def test_non_html_renderer(mocker):
    view = mocker.sentinel.view
    renderer = types.SimpleNamespace(name="foo.txt")
    info = types.SimpleNamespace(options={"renderer": renderer})

    assert derivers.html_cache_deriver(view, info) == view


def test_no_origin_cache_found(pyramid_request, mocker):
    view_result = mocker.sentinel.view_result
    view = mocker.Mock(return_value=view_result)
    renderer = types.SimpleNamespace(name="foo.html")
    info = types.SimpleNamespace(options={"renderer": renderer})
    context = mocker.sentinel.context
    add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

    # IOriginCache is unregistered, so the real find_service raises LookupError
    assert (
        derivers.html_cache_deriver(view, info)(context, pyramid_request) == view_result
    )
    add_response_callback.assert_not_called()


def test_response_hook(pyramid_request, mocker):
    cacher = mocker.Mock(spec=["cache"])
    response = mocker.sentinel.response
    view = mocker.Mock(return_value=response)
    context = mocker.sentinel.context
    mocker.patch.object(pyramid_request, "find_service", return_value=cacher)
    info = types.SimpleNamespace(
        options={"renderer": types.SimpleNamespace(name="foo.html")}
    )
    derived_view = derivers.html_cache_deriver(view, info)

    assert derived_view(context, pyramid_request) is response
    view.assert_called_once_with(context, pyramid_request)
    assert len(pyramid_request.response_callbacks) == 1

    pyramid_request.response_callbacks[0](pyramid_request, response)

    cacher.cache.assert_called_once_with(
        ["all-html", "foo.html"], pyramid_request, response
    )
