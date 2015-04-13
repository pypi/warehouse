# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest import mock

import fs.opener
import pretend
import pytest

from pyramid import renderers
from pyramid.httpexceptions import HTTPMovedPermanently

from warehouse import config


class TestCSPTween:

    def test_csp_policy(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(
            settings={
                "csp": {
                    "default-src": ["*"],
                    "style-src": ["'self'", "example.net"],
                },
            },
        )

        tween = config.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(path="/project/foobar/")

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy":
                "default-src *; style-src 'self' example.net",
        }

    def test_csp_policy_debug_disables(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(
            settings={
                "csp": {
                    "default-src": ["*"],
                    "style-src": ["'self'", "example.net"],
                },
            },
        )

        tween = config.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(path="/_debug_toolbar/foo/")

        assert tween(request) is response
        assert response.headers == {}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/foo/bar/", True),
        ("/static/wat/", False),
        ("/_debug_toolbar/thing/", False),
    ],
)
def test_activate_hook(path, expected):
    request = pretend.stub(path=path)
    assert config.activate_hook(request) == expected


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {},
        {"my settings": "the settings value"},
        {"yml.locations": ["/foo/"]},
    ],
)
def test_configure(monkeypatch, settings):
    fs_obj = pretend.stub()
    opener = pretend.call_recorder(lambda path, create_dir: fs_obj)
    monkeypatch.setattr(fs.opener, "fsopendir", opener)

    json_renderer_obj = pretend.stub()
    json_renderer_cls = pretend.call_recorder(lambda **kw: json_renderer_obj)
    monkeypatch.setattr(renderers, "JSON", json_renderer_cls)

    class FakeRegistry(dict):
        def __init__(self):
            self.settings = {
                "camo.url": "http://camo.example.com/",
                "pyramid.reload_assets": False,
                "dirs.packages": "/srv/data/pypi/packages/",
            }

    configurator_settings = {}
    configurator_obj = pretend.stub(
        registry=FakeRegistry(),
        include=pretend.call_recorder(lambda include: None),
        add_renderer=pretend.call_recorder(lambda name, renderer: None),
        add_jinja2_renderer=pretend.call_recorder(lambda renderer: None),
        add_jinja2_search_path=pretend.call_recorder(lambda path, name: None),
        get_settings=lambda: configurator_settings,
        add_settings=pretend.call_recorder(
            lambda d: configurator_settings.update(d)
        ),
        add_tween=pretend.call_recorder(lambda tween_factory: None),
        add_notfound_view=pretend.call_recorder(lambda append_slash: None),
        add_static_view=pretend.call_recorder(
            lambda name, path, cachebust: None
        ),
        scan=pretend.call_recorder(lambda ignore: None),
    )
    configurator_cls = pretend.call_recorder(lambda settings: configurator_obj)
    monkeypatch.setattr(config, "Configurator", configurator_cls)

    cachebuster_obj = pretend.stub()
    cachebuster_cls = pretend.call_recorder(lambda m, cache: cachebuster_obj)
    monkeypatch.setattr(config, "WarehouseCacheBuster", cachebuster_cls)

    config_defaults = pretend.call_recorder(lambda config, files: None)
    monkeypatch.setattr(config, "config_defaults", config_defaults)

    transaction_manager = pretend.stub()
    transaction = pretend.stub(
        TransactionManager=pretend.call_recorder(lambda: transaction_manager),
    )
    monkeypatch.setattr(config, "transaction", transaction)

    result = config.configure(settings=settings)

    if settings is None:
        expected_settings = {}
    else:
        expected_settings = settings.copy()

    assert configurator_cls.calls == [pretend.call(settings=expected_settings)]
    assert config_defaults.calls == [
        pretend.call(configurator_obj, ["warehouse:etc"]),
    ]
    assert result is configurator_obj
    assert configurator_obj.include.calls == [
        pretend.call("tzf.pyramid_yml"),
        pretend.call(".logging"),
        pretend.call("pyramid_jinja2"),
        pretend.call("pyramid_tm"),
        pretend.call("pyramid_services"),
        pretend.call(".legacy.action_routing"),
        pretend.call(".i18n"),
        pretend.call(".db"),
        pretend.call(".sessions"),
        pretend.call(".cache.http"),
        pretend.call(".cache.origin"),
        pretend.call(".csrf"),
        pretend.call(".accounts"),
        pretend.call(".packaging"),
        pretend.call(".redirects"),
        pretend.call(".routes"),
    ]
    assert configurator_obj.add_jinja2_renderer.calls == [
        pretend.call(".html"),
    ]
    assert configurator_obj.add_jinja2_search_path.calls == [
        pretend.call("warehouse:templates", name=".html"),
    ]
    assert configurator_obj.add_settings.calls == [
        pretend.call({
            "tm.manager_hook": mock.ANY,
            "tm.activate_hook": config.activate_hook,
        }),
        pretend.call({
            "csp": {
                "default-src": ["'none'"],
                "frame-ancestors": ["'none'"],
                "img-src": [
                    "'self'",
                    "http://camo.example.com/",
                    "https://secure.gravatar.com",
                    "https://raw.githubusercontent.com",
                ],
                "referrer": ["cross-origin"],
                "reflected-xss": ["block"],
                "script-src": ["'self'"],
                "style-src": ["'self'"],
            },
        }),
    ]
    add_settings_dict = configurator_obj.add_settings.calls[0].args[0]
    assert add_settings_dict["tm.manager_hook"](pretend.stub()) is \
        transaction_manager
    assert configurator_obj.add_tween.calls == [
        pretend.call("warehouse.config.content_security_policy_tween_factory"),
    ]
    assert configurator_obj.registry["filesystems"] == {"packages": fs_obj}
    assert configurator_obj.add_static_view.calls == [
        pretend.call(
            name="static",
            path="warehouse:static",
            cachebust=cachebuster_obj,
        ),
    ]
    assert cachebuster_cls.calls == [
        pretend.call("warehouse:static/manifest.json", cache=True),
    ]
    assert configurator_obj.scan.calls == [
        pretend.call(ignore=["warehouse.migrations.env"]),
    ]
    assert opener.calls == [
        pretend.call("/srv/data/pypi/packages/", create_dir=True),
    ]
    assert configurator_obj.add_notfound_view.calls == [
        pretend.call(append_slash=HTTPMovedPermanently),
    ]
    assert configurator_obj.add_renderer.calls == [
        pretend.call("json", json_renderer_obj),
    ]

    assert json_renderer_cls.calls == [
        pretend.call(sort_keys=True, separators=(",", ":")),
    ]
