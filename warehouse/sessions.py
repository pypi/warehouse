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

from werkzeug.contrib.sessions import SessionStore, Session as _Session

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
        # Ensure we have a valid key, if not generate a new one
        if not self.is_valid_key(sid):
            return self.new()

        # Fetch the serialized data from redis
        bdata = self.redis.get(self._redis_key(sid))

        # If the session doesn't exist in redis, we'll give the user a new
        # session
        if bdata is None:
            return self.new()

        try:
            data = msgpack.unpackb(bdata, encoding="utf8", use_list=True)
        except (
                msgpack.exceptions.UnpackException,
                msgpack.exceptions.ExtraData):
            # If the session data was invalid we'll give the user a new session
            return self.new()

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


class Session(_Session):

    def __init__(self, *args, **kwargs):
        super(Session, self).__init__(*args, **kwargs)

        self.cycled = False
        self.deleted = False

    def cycle(self):
        self.cycled = True

    def delete(self):
        self.deleted = True


def handle_session(fn):

    @functools.wraps(fn)
    def wrapped(self, view, app, request, *args, **kwargs):
        # Short little alias for the session store to make it easier to refer
        # to
        store = app.session_store

        # Look up the session id from the request, and either create a new
        # session or fetch the existing one from the session store
        sid = request.cookies.get(SESSION_COOKIE_NAME, None)
        session = store.new() if sid is None else store.get(sid)

        # Stick the session on the request, but in a private variable. If
        # a view wants to use the session it should use @uses_session to move
        # it to request.session and appropriately vary by Cookie
        request._session = session

        # Call our underlying function in order to get the response to this
        # request
        resp = fn(self, view, app, request, *args, **kwargs)

        # Check to see if the session has been marked to be deleted, if it has
        # tell our session store to delete it, and tell our response to delete
        # the session cookie as well, and then finally short circuit and return
        # our response.
        if session.deleted:
            # Delete in our session store
            store.delete(session)

            # Delete the cookie in the browser
            resp.delete_cookie(SESSION_COOKIE_NAME)

        # Check to see if the session has been marked to be cycled or not.
        # When cycling a session we copy all of the data into a new session
        # and delete the old one.
        if session.cycled:
            session = store.cycle(session)

        # Check to see if the session has been marked to be saved, generally
        # this means that the session data has been modified and thus we need
        # to store the new data.
        if session.should_save:
            store.save(session)

            # Whenever we store new data for our session, we want to issue a
            # new Set-Cookie header so that our expiration date for this
            # session gets reset.
            resp.set_cookie(
                SESSION_COOKIE_NAME,
                session.sid,
                secure=request.is_secure,
                httponly=True,
            )

        # Finally return our response
        return resp

    # Set an attribute so that we can verify the dispatch_view has had session
    # support enabled
    wrapped._sessions_handled = True

    return wrapped


def uses_session(fn):

    @functools.wraps(fn)
    @vary_by("Cookie")
    def wrapper(app, request, *args, **kwargs):
        # Add the session onto the request object
        request.session = request._session

        # Call the underlying function
        return fn(app, request, *args, **kwargs)

    return wrapper
