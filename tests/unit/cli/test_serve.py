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
        wsgi_app = pretend.stub()
        options = pretend.stub()
        app = Application(wsgi_app, options=options)
        assert app.options is options
        assert app.application is wsgi_app

    def test_load_config(self):
        options = {
            "foo": "another bar",
            "no": "yes",
        }
        app = Application(pretend.stub, options=options)
        settings = {"foo": "bar", "wat": "lol"}
        app.cfg = pretend.stub(
            settings=settings,
            set=settings.__setitem__,
        )
        app.load_config()
        assert settings == {"foo": "another bar", "wat": "lol"}

    def test_load(self):
        wsgi_app = pretend.stub()
        app = Application(wsgi_app, options={})
        assert app.load() is wsgi_app


class TestServe:

    def test_without_gunicorn(self, monkeypatch, cli):
        monkeypatch.setattr(warehouse.cli.serve, "HAS_GUNICORN", False)
        config = pretend.stub()
        result = cli.invoke(serve, obj=config)
        assert result.exit_code == 1
        assert result.output == (
            "Error: Cannot use 'warehouse serve' without gunicorn installed.\n"
        )

    def test_with_gunicorn(self, monkeypatch, cli):
        app_obj = pretend.stub(run=pretend.call_recorder(lambda: None))
        app_cls = pretend.call_recorder(lambda app, options: app_obj)
        mp = pretend.stub(cpu_count=lambda: 1)
        monkeypatch.setattr(warehouse.cli.serve, "HAS_GUNICORN", True)
        monkeypatch.setattr(warehouse.cli.serve, "Application", app_cls)
        monkeypatch.setattr(warehouse.cli.serve, "multiprocessing", mp)

        wsgi_app = pretend.stub()
        config = pretend.stub(
            make_wsgi_app=pretend.call_recorder(lambda: wsgi_app),
        )

        result = cli.invoke(serve, obj=config)

        assert result.exit_code == 0
        assert app_cls.calls == [
            pretend.call(
                wsgi_app,
                options={
                    "bind": None,
                    "reload": False,
                    "workers": 3,
                    "proc_name": "warehouse",
                },
            ),
        ]
        assert app_obj.run.calls == [pretend.call()]
