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

import pretend
import pytest

from warehouse import config
from warehouse.utils.mapper import WarehouseMapper


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
    configurator_settings = {}
    configurator_obj = pretend.stub(
        registry=pretend.stub(settings={"pyramid.reload_assets": False}),
        set_view_mapper=pretend.call_recorder(lambda mapper: None),
        include=pretend.call_recorder(lambda include: None),
        add_jinja2_renderer=pretend.call_recorder(lambda renderer: None),
        add_jinja2_search_path=pretend.call_recorder(lambda path, name: None),
        get_settings=lambda: configurator_settings,
        add_settings=pretend.call_recorder(
            lambda d: configurator_settings.update(d)
        ),
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
    assert configurator_obj.set_view_mapper.calls == [
        pretend.call(WarehouseMapper),
    ]
    assert configurator_obj.include.calls == [
        pretend.call("tzf.pyramid_yml"),
        pretend.call("pyramid_jinja2"),
        pretend.call("pyramid_tm"),
        pretend.call("pyramid_services"),
        pretend.call(".i18n"),
        pretend.call(".db"),
        pretend.call(".sessions"),
        pretend.call(".csrf"),
        pretend.call(".accounts"),
        pretend.call(".packaging"),
        pretend.call(".routes"),
    ]
    assert configurator_obj.add_jinja2_renderer.calls == [
        pretend.call(".html"),
    ]
    assert configurator_obj.add_jinja2_search_path.calls == [
        pretend.call("warehouse:templates", name=".html"),
    ]
    assert configurator_obj.add_settings.calls == [
        pretend.call({"tm.manager_hook": mock.ANY}),
    ]
    add_settings_dict = configurator_obj.add_settings.calls[0].args[0]
    assert add_settings_dict["tm.manager_hook"](pretend.stub()) is \
        transaction_manager
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
