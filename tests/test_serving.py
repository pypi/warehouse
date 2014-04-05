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

from warehouse import serving
from warehouse.serving import WSGIRequestHandler


def test_request_handler_log(monkeypatch):
    _log = pretend.call_recorder(lambda *a, **kw: None)

    monkeypatch.setattr(serving, "_log", _log)
    monkeypatch.setattr(WSGIRequestHandler, "__init__", lambda *a, **kw: None)

    handler = WSGIRequestHandler()
    handler.address_string = pretend.call_recorder(lambda: "127.0.0.1")

    handler.log("info", "test message")

    assert _log.calls == [pretend.call("info", "127.0.0.1 - test message\n")]
    assert handler.address_string.calls == [pretend.call()]
