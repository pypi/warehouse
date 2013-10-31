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

import psycopg2.extensions
import pytz


class PyTZCursor(psycopg2.extensions.cursor):

    def __init__(self, *args, **kwargs):
        super(PyTZCursor, self).__init__(*args, **kwargs)

        self.tzinfo_factory = pytz.FixedOffset


class TimeZoneListener(object):

    def connect(self, dbapi_con, con_record):
        dbapi_con.cursor_factory = PyTZCursor

    def checkout(self, dbapi_con, con_record, con_proxy):
        cursor = dbapi_con.cursor()
        cursor.execute("SET TIME ZONE UTC")
