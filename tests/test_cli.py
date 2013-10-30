# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import mock
import pretend

import webassets.ext.jinja2
import webassets.script
import werkzeug.serving

from warehouse.cli import ServeCommand, CollectStaticCommand
from warehouse.serving import WSGIRequestHandler


def test_serve(monkeypatch):
    run_simple = pretend.call_recorder(
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(werkzeug.serving, "run_simple", run_simple)

    host, port, app, use_reloader, use_debugger = (
        pretend.stub() for x in range(5)
    )
    ServeCommand()(
        app, host, port,
        reloader=use_reloader,
        debugger=use_debugger,
    )

    assert run_simple.calls == [
        pretend.call(
            host, port, app,
            use_reloader=use_reloader,
            use_debugger=use_debugger,
            request_handler=WSGIRequestHandler,
        ),
    ]


def test_collect_static(monkeypatch):
    run_build = pretend.call_recorder(lambda production: None)
    BuildCommand = pretend.call_recorder(lambda env: run_build)

    bundles = [pretend.stub()]
    load_bundles = pretend.call_recorder(lambda: bundles)
    jinja2_class = pretend.stub(load_bundles=load_bundles)
    Jinja2Loader = pretend.call_recorder(lambda env, dirs, jenvs: jinja2_class)

    monkeypatch.setattr(webassets.script, "BuildCommand", BuildCommand)
    monkeypatch.setattr(webassets.ext.jinja2, "Jinja2Loader", Jinja2Loader)

    app = pretend.stub(
        config=pretend.stub(debug=False),
        templates=pretend.stub(
            assets_environment=pretend.stub(
                add=pretend.call_recorder(lambda *a: None),
            ),
        ),
    )

    CollectStaticCommand()(app)

    assert BuildCommand.calls == [pretend.call(mock.ANY)]
    assert run_build.calls == [pretend.call(production=True)]

    assert Jinja2Loader.calls == [
        pretend.call(
            app.templates.assets_environment,
            mock.ANY,
            [app.templates],
        ),
    ]
    assert load_bundles.calls == [pretend.call()]
