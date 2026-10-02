# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from warehouse.api import config


def test_strict_json_loads():
    assert config._strict_json_loads(b'{"value":["\\ud83d\\ude00",1.5]}') == {
        "value": ["😀", 1.5]
    }


@pytest.mark.parametrize(
    ("value", "exception", "match"),
    [
        ('{"value": NaN}', ValueError, "Invalid JSON constant: NaN"),
        ('{"value": 1e400}', ValueError, "outside the finite range"),
        ('{"value": "\\ud800"}', ValueError, "valid Unicode"),
        ('{"value": 1}'.encode("utf-16"), UnicodeDecodeError, "utf-8"),
    ],
)
def test_strict_json_loads_rejects_invalid_input(value, exception, match):
    with pytest.raises(exception, match=match):
        config._strict_json_loads(value)


def test_api_set_content_type(mocker):
    def view(context, request):
        return mocker.sentinel.response

    info = types.SimpleNamespace(options={"api_version": "v1"})
    wrapped_view = config._api_set_content_type(view, info)

    request = types.SimpleNamespace(response=types.SimpleNamespace(content_type=None))

    assert wrapped_view(None, request) is mocker.sentinel.response
    assert request.response.content_type == "application/vnd.pypi.v1+json"


def test_api_set_content_type_no_api_version(mocker):
    def view(context, request):
        return mocker.sentinel.response

    info = types.SimpleNamespace(options={})
    wrapped_view = config._api_set_content_type(view, info)

    request = types.SimpleNamespace(response=types.SimpleNamespace(content_type=None))

    assert wrapped_view(None, request) is mocker.sentinel.response
    assert request.response.content_type is None


@pytest.mark.parametrize("env_name", ["development", "production"])
def test_includeme(monkeypatch, env_name, mocker):
    # We use `str(Path(__file__).parent / 'openapi.yaml'` to get the path.
    # In our test, monkeypatch to a known value.
    monkeypatch.setattr(config, "__file__", "/mnt/dummy/config.py")

    conf = mocker.Mock(
        spec=[
            "add_view_deriver",
            "include",
            "pyramid_openapi3_spec",
            "pyramid_openapi3_add_deserializer",
            "pyramid_openapi3_add_explorer",
            "registry",
        ]
    )
    conf.registry.settings = {"warehouse.env": env_name}

    config.includeme(conf)

    conf.add_view_deriver.assert_called_once_with(config._api_set_content_type)
    conf.include.assert_called_once_with("pyramid_openapi3")
    conf.pyramid_openapi3_spec.assert_called_once_with(
        "/mnt/dummy/openapi.yaml", route="/api/openapi.yaml"
    )
    conf.pyramid_openapi3_add_deserializer.assert_called_once_with(
        "application/vnd.pypi.api-v0-danger+json", config._strict_json_loads
    )
    if env_name == "development":
        conf.pyramid_openapi3_add_explorer.assert_called_once_with(
            route="/api/explorer/"
        )
    else:
        conf.pyramid_openapi3_add_explorer.assert_not_called()
