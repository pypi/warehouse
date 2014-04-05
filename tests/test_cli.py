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

import pretend

import werkzeug.serving

from warehouse.cli import ServeCommand
from warehouse.serving import WSGIRequestHandler


def test_serve(monkeypatch, tmpdir):
    run_simple = pretend.call_recorder(
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(werkzeug.serving, "run_simple", run_simple)

    with open(str(tmpdir.join("foo.txt")), "w") as fp:
        fp.write("text file")

    app = pretend.stub(static_dir=str(tmpdir))
    host, port, use_reloader, use_debugger = (pretend.stub() for x in range(4))

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
            extra_files=[str(tmpdir.join("foo.txt"))],
        ),
    ]
