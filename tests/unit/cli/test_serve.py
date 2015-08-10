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

import pretend

import warehouse.cli.serve

from warehouse.cli.serve import Application, serve


class TestApplication:

    def test_basic_setup(self):
        configurator = pretend.stub()
        options = pretend.stub(items=lambda: [])
        app = Application(configurator, options=options)
        assert app.options is options
        assert app.configurator is configurator

    def test_load_config(self):
        options = {
            "foo": "another bar",
            "no": "yes",
        }
        app = Application(pretend.stub(), options=options)
        settings = {"foo": "bar", "wat": "lol"}
        app.cfg = pretend.stub(
            settings=settings,
            set=settings.__setitem__,
        )
        app.load_config()
        assert settings == {"foo": "another bar", "wat": "lol"}

    def test_load(self):
        wsgi_app = pretend.stub()
        configurator = pretend.stub(
            make_wsgi_app=pretend.call_recorder(lambda: wsgi_app),
        )
        app = Application(configurator, options={})
        assert app.load() is wsgi_app
        assert configurator.make_wsgi_app.calls == [pretend.call()]


def test_serve(monkeypatch, cli):
    app_obj = pretend.stub(run=pretend.call_recorder(lambda: None))
    app_cls = pretend.call_recorder(lambda app, options: app_obj)
    mp = pretend.stub(cpu_count=lambda: 1)
    monkeypatch.setattr(warehouse.cli.serve, "Application", app_cls)
    monkeypatch.setattr(warehouse.cli.serve, "multiprocessing", mp)

    config = pretend.stub()

    result = cli.invoke(serve, obj=config)

    assert result.exit_code == 0
    assert app_cls.calls == [
        pretend.call(
            config,
            options={
                "reload": False,
                "workers": 3,
                "proc_name": "warehouse",
                "forwarded_allow_ips": "*",
            },
        ),
    ]
    assert app_obj.run.calls == [pretend.call()]
