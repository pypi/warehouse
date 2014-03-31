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
from werkzeug.contrib.sessions import Session as _Session
from werkzeug.utils import dump_cookie, parse_cookie
from werkzeug.wsgi import ClosingIterator


class Session(_Session):

    def __init__(self, *args, **kwargs):
        super(Session, self).__init__(*args, **kwargs)

        self.cycled = False

    def cycle(self):
        self.cycled = True


class SessionMiddleware(object):
    """
    A simple middleware that puts the session object of a store provided
    into the WSGI environ. It automatically sets cookies and restores
    sessions.
    """

    def __init__(self, app, store, cookie_name="session_id",
                 cookie_age=None, cookie_expires=None, cookie_path="/",
                 cookie_domain=None, cookie_secure=None,
                 cookie_httponly=False, environ_key="warehouse.session"):
        self.app = app
        self.store = store
        self.cookie_name = cookie_name
        self.cookie_age = cookie_age
        self.cookie_expires = cookie_expires
        self.cookie_path = cookie_path
        self.cookie_domain = cookie_domain
        self.cookie_secure = cookie_secure
        self.cookie_httponly = cookie_httponly
        self.environ_key = environ_key

    def __call__(self, environ, start_response):
        cookie = parse_cookie(environ.get("HTTP_COOKIE", ""))
        sid = cookie.get(self.cookie_name, None)
        if sid is None:
            session = self.store.new()
        else:
            session = self.store.get(sid)

        environ[self.environ_key] = session

        def injecting_start_response(status, headers, exc_info=None):
            # We want to modify the session variable from __call__
            nonlocal session

            # Check to see if the session has been marked to be cycled or not.
            # When cycling a session we copy all of the data into a new session
            # and delete the old one.
            if session.cycled:
                # Create a new session with all of the data from the old one
                new_session = self.store.new()
                new_session.update(session)

                # Delete the old session now that we've copied the data
                self.store.delete(session)

                # Reference our old session with the new one
                session = new_session

            if session.should_save:
                self.store.save(session)
                headers.append(('Set-Cookie', dump_cookie(self.cookie_name,
                                session.sid, self.cookie_age,
                                self.cookie_expires, self.cookie_path,
                                self.cookie_domain, self.cookie_secure,
                                self.cookie_httponly)))
            return start_response(status, headers, exc_info)
        return ClosingIterator(self.app(environ, injecting_start_response),
                               lambda: self.store.save_if_modified(session))
