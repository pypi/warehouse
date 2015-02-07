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
import hmac
import time
import urllib.parse

import msgpack
import msgpack.exceptions
import redis

from pyramid.config.views import DefaultViewMapper
from pyramid.httpexceptions import HTTPForbidden, HTTPMethodNotAllowed
from pyramid.interfaces import ISession, ISessionFactory, IViewMapperFactory
from pyramid.tweens import EXCVIEW
from zope.interface import implementer

from warehouse.utils import crypto


REASON_NO_ORIGIN = "Origin checking failed - no Origin or Referer."
REASON_BAD_ORIGIN = "Origin checking failed - {} does not match {}."
REASON_BAD_TOKEN = "CSRF token missing or incorrect."


class InvalidCSRF(HTTPForbidden):
    pass


def _add_vary(request, response):
    vary = set(response.vary if response.vary is not None else [])
    vary |= {"Cookie"}
    response.vary = vary


def uses_session(view):
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        # Set a callback to add the Vary header to any view that adds the
        # Vary: Cookie header to every response.
        request.add_response_callback(_add_vary)

        # We want to restore the session object to the request.session location
        # because this view is allowed to use the session.
        request.session = request._session

        # Call our view with our now modified request.
        return view(request, *args, **kwargs)

    return wrapped


def session_tween_factory(handler, registry):
    def session_tween(request):
        # Stash our real session object in a private location on the request so
        # we can access it later.
        request._session = request.session

        # Set our request.session to an InvalidSession() which will raise
        # errors anytime someone attempts to use it.
        request.session = InvalidSession()

        # Call our handler with the request, and no matter what ensure that
        # after we've called it that the request.session has been set back to
        # it's real value.
        try:
            return handler(request)
        finally:
            request.session = request._session

    return session_tween


def csrf_exempt(view):
    view._process_csrf = False
    return view


def csrf_protect(view):
    view._process_csrf = True
    return view


def _changed_method(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        self.changed()
        return method(self, *args, **kwargs)
    return wrapped


def _invalid_method(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        self._error_message()
    return wrapped


@implementer(ISession)
class InvalidSession(dict):

    __contains__ = _invalid_method(dict.__contains__)
    __delitem__ = _invalid_method(dict.__delitem__)
    __getitem__ = _invalid_method(dict.__getitem__)
    __iter__ = _invalid_method(dict.__iter__)
    __len__ = _invalid_method(dict.__len__)
    __setitem__ = _invalid_method(dict.__setitem__)
    clear = _invalid_method(dict.clear)
    copy = _invalid_method(dict.copy)
    fromkeys = _invalid_method(dict.fromkeys)
    get = _invalid_method(dict.get)
    items = _invalid_method(dict.items)
    keys = _invalid_method(dict.keys)
    pop = _invalid_method(dict.pop)
    popitem = _invalid_method(dict.popitem)
    setdefault = _invalid_method(dict.setdefault)
    update = _invalid_method(dict.update)
    values = _invalid_method(dict.values)

    def _error_message(self):
        raise RuntimeError(
            "Cannot use request.session in a view without @uses_session."
        )

    def __getattr__(self, name):
        self._error_message()


@implementer(ISession)
class Session(dict):

    _csrf_token_key = "_csrf_token"

    # A number of our methods need to be decorated so that they also call
    # self.changed()
    __delitem__ = _changed_method(dict.__delitem__)
    __setitem__ = _changed_method(dict.__setitem__)
    clear = _changed_method(dict.clear)
    pop = _changed_method(dict.pop)
    popitem = _changed_method(dict.popitem)
    setdefault = _changed_method(dict.setdefault)
    update = _changed_method(dict.update)

    def __init__(self, data=None, session_id=None, new=True):
        # Brand new sessions don't have any data, so we'll just create an empty
        # dictionary for them.
        if data is None:
            data = {}

        # Initialize our actual dictionary here.
        super().__init__(data)

        # We need to track the state of our Session.
        self._sid = session_id
        self._changed = False
        self.new = new
        self.created = int(time.time())
        self.cycled = False
        self.invalidated = False

    @property
    def sid(self):
        if self._sid is None:
            self._sid = crypto.random_token()
        return self._sid

    @sid.deleter
    def sid(self):
        self._sid = None

    def changed(self):
        self._changed = True

    def cycle(self):
        self.cycled = True

    def invalidate(self):
        self.clear()
        self.new = True
        self.created = int(time.time())
        self.invalidated = True
        self.cycled = False
        self._changed = False

    def should_save(self):
        return self._changed or self.cycled

    # Flash Messages Methods
    def flash(msg, queue="", allow_duplicate=True):
        raise NotImplementedError

    def peek_flash(queue=""):
        raise NotImplementedError

    def pop_flash(queue=""):
        raise NotImplementedError

    # CSRF Methods
    def new_csrf_token(self):
        self[self._csrf_token_key] = crypto.random_token()
        return self[self._csrf_token_key]

    def get_csrf_token(self):
        token = self.get(self._csrf_token_key)
        if token is None:
            token = self.new_csrf_token()
        return token

    def has_csrf_token(self):
        return self._csrf_token_key in self


@implementer(ISessionFactory)
class SessionFactory:

    cookie_name = "session_id"
    max_age = 12 * 60 * 60  # 12 hours

    def __init__(self, secret, url):
        self.redis = redis.StrictRedis.from_url(url)
        self.signer = crypto.TimestampSigner(secret, salt="session")

    def __call__(self, request):
        return self._process_request(request)

    def _redis_key(self, session_id):
        return "warehouse/session/data/{}".format(session_id)

    def _process_request(self, request):
        # Register a callback with the request so we can save the session once
        # it's finished.
        request.add_response_callback(self._process_response)

        # Load our session ID from the request.
        session_id = request.cookies.get(self.cookie_name)

        # If we do not have a session ID then we'll just use a new empty
        # session.
        if session_id is None:
            return Session()

        # Check to make sure we have a valid session id
        try:
            session_id = self.signer.unsign(session_id, max_age=self.max_age)
            session_id = session_id.decode("utf8")
        except crypto.BadSignature:
            return Session()

        # Fetch the serialized data from redis
        bdata = self.redis.get(self._redis_key(session_id))

        # If the session didn't exist in redis, we'll give the user a new
        # session.
        if bdata is None:
            return Session()

        # De-serialize our session data
        try:
            data = msgpack.unpackb(bdata, encoding="utf8", use_list=True)
        except (msgpack.exceptions.UnpackException,
                msgpack.exceptions.ExtraData):
            # If the session data was invalid we'll give the user a new session
            return Session()

        # If we were able to load existing session data, load it into a
        # Session class
        session = Session(data, session_id)

        return session

    def _process_response(self, request, response):
        # Check to see if the session has been marked to be deleted, if it has
        # benn then we'll delete it, and tell our response to delete the
        # session cookie as well.
        if request.session.invalidated:
            self.redis.delete(self._redis_key(request.session.sid))
            del request.session.sid
            if not request.session.should_save():
                response.delete_cookie(self.cookie_name)

        # Check to see if the session has been marked to be cycled or not.
        # When cycling a session we copy all of the data into a new session
        # and delete the old one.
        if request.session.cycled:
            # Create a new session and copy all of the data into it.
            new_session = Session()
            new_session.update(request.session)

            # Delete the old session now that we've copied the data
            self.redis.delete(self._redis_key(request.session.sid))

            # Set our new session as the session of the request.
            request.session = new_session

        # Check to see if the session has been marked to be saved, generally
        # this means that the session data has been modified and thus we need
        # to store the new data.
        if request.session.should_save():
            # Save our session in Redis
            self.redis.setex(
                self._redis_key(request.session.sid),
                self.max_age,
                msgpack.packb(
                    request.session,
                    encoding="utf8",
                    use_bin_type=True,
                ),
            )

            # Send our session cookie to the client
            response.set_cookie(
                self.cookie_name,
                self.signer.sign(request.session.sid.encode("utf8")),
                max_age=self.max_age,
                httponly=True,
                secure=request.scheme == "https",
            )


def csrf_mapper_factory(mapper):
    class CSRFMapper(mapper):

        def __call__(self, view):
            view = super().__call__(view)

            # Check if the view has CSRF exempted, and if it is then we just
            # want to return the view without wrapping it.
            if not getattr(view, "_process_csrf", True):
                return view

            @functools.wraps(view)
            def wrapped(context, request):
                # If we're processing CSRF for this view, then we want to
                # set a Vary: Cookie header on every response to ensure that
                # we don't cache the result of a CSRF check or a form with a
                # CSRF token in it.
                if getattr(view, "_process_csrf", None):
                    request.add_response_callback(_add_vary)

                # Assume that anything not defined as 'safe' by RFC2616 needs
                # protection
                if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
                    # Determine if this view has set itself so that it should
                    # be protected against CSRF. If it has not and it's gotten
                    # one of these methods, then we want to raise an error
                    # stating that this resource does not support this method.
                    if not getattr(view, "_process_csrf", None):
                        raise HTTPMethodNotAllowed

                    if request.scheme == "https":
                        # Determine the origin of this request
                        origin = request.headers.get("Origin")
                        if origin is None:
                            origin = request.headers.get("Referer")

                        # Fail if we were not able to locate an origin at all
                        if not origin:
                            raise InvalidCSRF(REASON_NO_ORIGIN)

                        # Parse the origin and host for comparison
                        originp = urllib.parse.urlparse(origin)
                        hostp = urllib.parse.urlparse(request.host_url)

                        # Actually check our Origin against our Current
                        # Host URL.
                        if ((originp.scheme, originp.hostname, originp.port)
                                != (hostp.scheme, hostp.hostname, hostp.port)):
                            reason_origin = origin
                            if origin != "null":
                                reason_origin = urllib.parse.urlunparse(
                                    originp[:2] + ("", "", "", ""),
                                )

                            reason = REASON_BAD_ORIGIN.format(
                                reason_origin, request.host_url,
                            )

                            raise InvalidCSRF(reason)

                    session = getattr(request, "_session", request.session)

                # Get the provided CSRF token from the request.
                request_token = request.POST.get("csrf_token")
                if not request_token:
                    request_token = request.headers.get("CSRFToken")

                # Get our CSRF token from the session
                csrf_token = session.get_csrf_token()

                if not hmac.compare_digest(csrf_token, request_token):
                    raise InvalidCSRF(REASON_BAD_TOKEN)

                return view(context, request)

            return wrapped
    return CSRFMapper


def includeme(config):
    config.set_session_factory(
        SessionFactory(
            config.registry["config"].sessions.secret,
            config.registry["config"].sessions.url,
        ),
    )
    config.add_tween("warehouse.sessions.session_tween_factory", under=EXCVIEW)

    # We need to commit what's happened so far so that we can get the current
    # default ViewMapper
    config.commit()

    # Get the current default ViewMapper, and create a subclass of it that
    # will wrap our view with CSRF checking.
    mapper = config.registry.queryUtility(IViewMapperFactory)
    if mapper is None:
        mapper = DefaultViewMapper
    config.set_view_mapper(csrf_mapper_factory(mapper))
