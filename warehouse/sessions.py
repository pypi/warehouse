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

from werkzeug.contrib.sessions import Session as _Session

from warehouse.utils import vary_by


class Session(_Session):

    def __init__(self, *args, **kwargs):
        super(Session, self).__init__(*args, **kwargs)

        self.cycled = False

    def cycle(self):
        self.cycled = True


def handle_session(fn):

    @functools.wraps(fn)
    def wrapped(self, view, app, request, *args, **kwargs):
        # Short little alias for the session store to make it easier to refer
        # to
        store = app.session_store

        # Look up the session id from the request, and either create a new
        # session or fetch the existing one from the session store
        sid = request.cookies.get("session_id", None)
        session = store.new() if sid is None else store.get(sid)

        # Stick the session on the request, but in a private variable. If
        # a view wants to use the session it should use @uses_session to move
        # it to request.session and appropriately vary by Cookie
        request._session = session

        # Call our underlying function in order to get the response to this
        # request
        resp = fn(self, view, app, request, *args, **kwargs)

        # Check to see if the session has been marked to be cycled or not.
        # When cycling a session we copy all of the data into a new session
        # and delete the old one.
        if session.cycled:
            # Create a new session with all of the data from the old one
            new_session = store.new()
            new_session.update(session)

            # Delete the old session now that we've copied the data
            store.delete(session)

            # Reference our old session with the new one
            session = new_session

        # Check to see if the session has been marked to be saved, generally
        # this means that the session data has been modified and thus we need
        # to store the new data.
        if session.should_save:
            store.save(session)

            # Whenever we store new data for our session, we want to issue a
            # new Set-Cookie header so that our expiration date for this
            # session gets reset.
            resp.set_cookie(
                "session_id",
                session.sid,
                secure=request.is_secure,
                httponly=True,
            )

        # Finally return our response
        return resp

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
