# Copyright 2014 Donald Stufft
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

from flask.sessions import SessionInterface


class FakeSession:

    """
    A Fake session that does nothing. We use properties to prevent assigning
    to them and actually doing something.
    """

    @property
    def permanent(self):
        return True

    @property
    def new(self):
        return False

    @property
    def modified(self):
        return False

    def _fail(self):
        raise RuntimeError(
            "An attempt to use the built in session handling of flask was "
            "detected. Do not use this, instead use warehouse.sessions."
        )

    def __setitem__(self, *args, **kwargs):
        self._fail()

    def __delitem__(self, *args, **kwargs):
        self._fail()

    def clear(self, *args, **kwargs):
        self._fail()

    def pop(self, *args, **kwargs):
        self._fail()

    def popitem(self, *args, **kwargs):
        self._fail()

    def update(self, *args, **kwargs):
        self._fail()

    def setdefault(self, *args, **kwargs):
        self._fail()


class FakeSessionInterface(SessionInterface):
    """
    A Fake session interface that just acts as a no-op. We use this because
    Flask should never ever touch our sessions.
    """

    null_session_class = FakeSession

    def is_null_session(self, obj):
        return True

    def should_set_cookie(self, app, session):
        return False

    def open_session(self, app, request):
        return
