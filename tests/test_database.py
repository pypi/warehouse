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

import pytz

from warehouse.database import TimeZoneListener, PyTZCursor


def test_timezone_cursor():
    cursor = PyTZCursor(None, None, None)
    assert cursor.tzinfo_factory is pytz.FixedOffset


def test_timezone_listener_connect():
    dbapi_conn = pretend.stub()
    con_record = pretend.stub()

    listener = TimeZoneListener()
    listener.connect(dbapi_conn, con_record)

    assert dbapi_conn.cursor_factory is PyTZCursor


def test_timezone_listener_checkout():
    cursor = pretend.stub(execute=pretend.call_recorder(lambda x: None))
    dbapi_conn = pretend.stub(cursor=pretend.call_recorder(lambda: cursor))
    con_record = pretend.stub()
    con_proxy = pretend.stub()

    listener = TimeZoneListener()
    listener.checkout(dbapi_conn, con_record, con_proxy)

    assert dbapi_conn.cursor.calls == [pretend.call()]
    assert cursor.execute.calls == [pretend.call("SET TIME ZONE UTC")]
