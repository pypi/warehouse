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

import pretend
import werkzeug.serving

from warehouse.cli import ServeCommand


def test_serve(monkeypatch):
    run_simple = pretend.call_recorder(
        lambda host, port, app, use_reloader, use_debugger: None,
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
        ),
    ]
