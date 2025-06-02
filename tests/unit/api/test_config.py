# SPDX-License-Identifier: Apache-2.0

import orjson
import pretend
import pytest

from warehouse.api import config


def test_api_set_content_type():
    response = pretend.stub()

    @pretend.call_recorder
    def view(context, request):
        return response

    info = pretend.stub(options={"api_version": "v1"})
    wrapped_view = config._api_set_content_type(view, info)

    context = pretend.stub()
    request = pretend.stub(response=pretend.stub(content_type=None))

    assert wrapped_view(context, request) is response
    assert request.response.content_type == "application/vnd.pypi.v1+json"


def test_api_set_content_type_no_api_version():
    response = pretend.stub()

    @pretend.call_recorder
    def view(context, request):
        return response

    info = pretend.stub(options={})
    wrapped_view = config._api_set_content_type(view, info)

    context = pretend.stub()
    request = pretend.stub(response=pretend.stub(content_type=None))

    assert wrapped_view(context, request) is response
    assert request.response.content_type is None


@pytest.mark.parametrize("env_name", ["development", "production"])
def test_includeme(monkeypatch, env_name):
    # We use `str(Path(__file__).parent / 'openapi.yaml'` to get the path.
    # In our test, monkeypatch to a known value.
    monkeypatch.setattr(config, "__file__", "/mnt/dummy/config.py")

    conf = pretend.stub(
        add_view_deriver=pretend.call_recorder(
            lambda deriver, over=None, under=None: None
        ),
        include=pretend.call_recorder(lambda x: None),
        pyramid_openapi3_spec=pretend.call_recorder(lambda *a, **kw: None),
        pyramid_openapi3_add_deserializer=pretend.call_recorder(lambda *a, **kw: None),
        pyramid_openapi3_add_explorer=pretend.call_recorder(lambda *a, **kw: None),
        registry=pretend.stub(settings={"warehouse.env": env_name}),
    )

    config.includeme(conf)

    assert conf.add_view_deriver.calls == [pretend.call(config._api_set_content_type)]
    assert conf.include.calls == [pretend.call("pyramid_openapi3")]
    assert conf.pyramid_openapi3_spec.calls == [
        pretend.call("/mnt/dummy/openapi.yaml", route="/api/openapi.yaml")
    ]
    assert conf.pyramid_openapi3_add_deserializer.calls == [
        pretend.call("application/vnd.pypi.api-v0-danger+json", orjson.loads)
    ]
    if env_name == "development":
        assert conf.pyramid_openapi3_add_explorer.calls == [
            pretend.call(route="/api/explorer/")
        ]
    else:
        assert not conf.pyramid_openapi3_add_explorer.calls
