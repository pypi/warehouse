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

import asyncio

from aiopg.sa import create_engine

import sqlalchemy


__all__ = ["includeme", "metadata"]


metadata = sqlalchemy.MetaData()


class _Database:

    def __init__(self, request):
        self.request = request
        self.conn = None

    @property
    def engine(self):
        if hasattr(self.request.registry, "engine"):
            return self.request.registry.engine

    @engine.setter
    def engine(self, value):
        self.request.registry.engine = value

    @asyncio.coroutine
    def execute(self, *args, **kwargs):
        # Figure out if we have a database connection already and if we do then
        # make sure it's not closed and if it isn't then just return that.
        if self.conn is None or self.conn.closed:
            # Figure out if we have an engine already, if we do not then create
            # one.
            if self.engine is None:
                self.engine = yield from create_engine(
                    self.request.config.database.url
                )

            # Acquire our database connection.
            self.conn = yield from self.engine.acquire()

            # Add a request finished callback to release the connection back
            # into the pool.
            self.request.add_finished_callback(self.close)

        return (yield from self.conn.execute(*args, **kwargs))

    def close(self, request):
        self.engine.release(self.conn)


def includeme(config):
    config.add_request_method(_Database, name="db", reify=True)
