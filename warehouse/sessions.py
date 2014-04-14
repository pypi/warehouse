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
import functools
import re

import msgpack
import msgpack.exceptions

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.contrib.sessions import SessionStore
from werkzeug.datastructures import CallbackDict

from warehouse.utils import random_token, vary_by


SESSION_COOKIE_NAME = "session_id"


class RedisSessionStore(SessionStore):

    valid_key_regex = re.compile(r"^[a-zA-Z0-9_-]{43}$")

    max_age = 12 * 60 * 60  # 12 hours

    def __init__(self, redis, session_class=None, _random_token=random_token):
        super(RedisSessionStore, self).__init__(session_class=session_class)

        self.redis = redis
        self._random_token = _random_token

    def _redis_key(self, sid):
        return "warehouse/session/data/{}".format(sid)

    def generate_key(self, salt=None):
        return self._random_token()

    def is_valid_key(self, key):
        return self.valid_key_regex.search(key) is not None

    def get(self, sid):
        """
        Return the session data or None if the sid is not valid, not found
        """
        if not self.is_valid_key(sid):
            # Ensure we have a valid key
            return None

        # Fetch the serialized data from redis
        bdata = self.redis.get(self._redis_key(sid))

        if bdata is None:
            # If the session doesn't exist in redis
            return None

        try:
            data = msgpack.unpackb(bdata, encoding="utf8", use_list=True)
        except (
                msgpack.exceptions.UnpackException,
                msgpack.exceptions.ExtraData):
            # If the session data was invalid we'll give the user a new session
            return None

        # If we were able to load existing session data, load it into a
        # Session class
        session = self.session_class(data, sid, False)

        # Refresh the session in redis to prevent early expiration
        self.refresh(session)

        # Finally return our saved session
        return session

    def save(self, session):
        # Save the session in redis
        self.redis.setex(
            self._redis_key(session.sid),
            self.max_age,
            msgpack.packb(session, encoding="utf8", use_bin_type=True),
        )

    def delete(self, session):
        # Delete the session in redis
        self.redis.delete(self._redis_key(session.sid))

    def refresh(self, session):
        # Refresh the session in redis
        self.redis.expire(self._redis_key(session.sid), self.max_age)

    def cycle(self, session):
        # Create a new session with all of the data from the old one
        new_session = self.new()
        new_session.update(session)

        # Delete the old session now that we've copied the data
        self.delete(session)

        # Return the new session
        return new_session


class Session(CallbackDict, SessionMixin):

    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial, on_update)

        self.sid = sid
        self.new = new

        # XXX: Perhaps call this to_cycle and to_delete
        self.cycled = False
        self.deleted = False

        self.modified = False

    def cycle(self):
        self.modified = True
        self.cycled = True

    def delete(self):
        # XXX: Re-evaluate if this has to be considered modification
        self.modified = True
        self.deleted = True


class RedisSessionInterface(SessionInterface):
    session_class = Session

    def __init__(self, session_store):
        self.session_store = session_store

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)

        if not sid:
            # If there is no session ID create a new session
            return self.session_store.new()

        val = self.session_store.get(sid)
        if val is not None:
            return val
        return self.session_store.new()

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        if session.deleted:
            self.session_store.delete(session)
            if session.modified:
                response.delete_cookie(app.session_cookie_name, domain=domain)
            return

        if session.cycled:
            session = self.session_store.cycle(session)

        if not session:
            return

        cookie_exp = self.get_expiration_time(app, session)
        self.session_store.save(session)
        response.set_cookie(
            app.session_cookie_name, session.sid,
            expires=cookie_exp, httponly=True,
            domain=domain
        )


def uses_session(fn):
    @functools.wraps(fn)
    @vary_by("Cookie")
    def wrapper(*args, **kwargs):
        # Call the underlying function
        return fn(*args, **kwargs)
    return wrapper
