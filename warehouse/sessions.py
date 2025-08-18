# SPDX-License-Identifier: Apache-2.0

import datetime
import functools
import time

import markupsafe
import msgpack
import msgpack.exceptions
import redis

from pyramid import viewderivers
from pyramid.interfaces import ISession, ISessionFactory
from zope.interface import implementer

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.accounts.views import USER_ID_INSECURE_COOKIE
from warehouse.cache.http import add_vary
from warehouse.utils import crypto
from warehouse.utils.msgpack import object_encode


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
            "Cannot use request.session in a view without uses_session=True."
        )

    def __getattr__(self, name):
        self._error_message()

    @property
    def created(self):
        self._error_message()


def _changed_method(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        self.changed()
        return method(self, *args, **kwargs)

    return wrapped


@implementer(ISession)
class Session(dict):
    _csrf_token_key = "_csrf_token"
    _flash_key = "_flash_messages"
    _totp_secret_key = "_totp_secret"
    _webauthn_challenge_key = "_webauthn_challenge"
    _reauth_timestamp_key = "_reauth_timestamp"
    _password_timestamp_key = "_password_timestamp"

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

        # We'll track all of the IDs that have been invalidated here
        self.invalidated = set()

    @property
    def sid(self):
        if self._sid is None:
            self._sid = crypto.random_token()
        return self._sid

    def changed(self):
        self._changed = True

    def invalidate(self):
        self.clear()
        self.new = True
        self.created = int(time.time())
        self._changed = False

        # If the current session id isn't None we'll want to record it as one
        # of the ones that have been invalidated.
        if self._sid is not None:
            self.invalidated.add(self._sid)
            self._sid = None

    def should_save(self):
        return self._changed

    def record_auth_timestamp(self):
        self[self._reauth_timestamp_key] = datetime.datetime.now().timestamp()
        self.changed()

    def record_password_timestamp(self, timestamp):
        self[self._password_timestamp_key] = timestamp
        self.changed()

    def password_outdated(self, current_password_timestamp):
        stored_password_timestamp = self.get(self._password_timestamp_key)

        if stored_password_timestamp is None:
            # This session predates invalidation by password reset... since
            # we cannot say for sure, let it live its life.
            return False

        return current_password_timestamp != stored_password_timestamp

    def needs_reauthentication(self, time_to_reauth):
        reauth_timestamp = self.get(self._reauth_timestamp_key, 0)
        current_time = datetime.datetime.now().timestamp()

        return current_time - reauth_timestamp >= time_to_reauth

    # Flash Messages Methods
    def _get_flash_queue_key(self, queue):
        return ".".join(filter(None, [self._flash_key, queue]))

    def flash(self, msg, queue="", allow_duplicate=True, safe=False):
        queue_key = self._get_flash_queue_key(queue)

        # If we're not allowing duplicates check if this message is already
        # in the queue, and if it is just return immediately.
        if not allow_duplicate and {"msg": msg, "safe": safe} in self.get(
            queue_key, []
        ):
            return

        self.setdefault(queue_key, []).append({"msg": msg, "safe": safe})

    def peek_flash(self, queue=""):
        return self.get(self._get_flash_queue_key(queue), [])

    def pop_flash(self, queue=""):
        queue_key = self._get_flash_queue_key(queue)
        messages = [
            markupsafe.Markup(m["msg"]) if m["safe"] else m["msg"]
            for m in self.get(queue_key, [])
        ]
        self.pop(queue_key, None)
        return messages

    # CSRF Methods
    def new_csrf_token(self):
        self[self._csrf_token_key] = crypto.random_token()
        return self[self._csrf_token_key]

    def get_csrf_token(self):
        token = self.get(self._csrf_token_key)
        if token is None:
            token = self.new_csrf_token()
        return token

    def get_totp_secret(self):
        totp_secret = self.get(self._totp_secret_key)
        if totp_secret is None:
            totp_secret = self[self._totp_secret_key] = otp.generate_totp_secret()
        return totp_secret

    def clear_totp_secret(self):
        self[self._totp_secret_key] = None

    def get_webauthn_challenge(self):
        webauthn_challenge = self.get(self._webauthn_challenge_key)
        if webauthn_challenge is None:
            self[self._webauthn_challenge_key] = webauthn.generate_webauthn_challenge()
            webauthn_challenge = self[self._webauthn_challenge_key]
        return webauthn_challenge

    def clear_webauthn_challenge(self):
        self[self._webauthn_challenge_key] = None


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
        return f"warehouse/session/data/{session_id}"

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
            data = msgpack.unpackb(bdata, raw=False, use_list=True)
        except (msgpack.exceptions.UnpackException, msgpack.exceptions.ExtraData):
            # If the session data was invalid we'll give the user a new session
            return Session()

        # If we were able to load existing session data, load it into a
        # Session class
        session = Session(data, session_id, False)

        return session

    def _process_response(self, request, response):
        # If the request has an InvalidSession, then the view can't have
        # accessed the session, and we can just skip all of this anyways.
        if isinstance(request.session, InvalidSession):
            return

        # Check to see if the session has been marked to be deleted, if it has
        # benn then we'll delete it, and tell our response to delete the
        # session cookie as well.
        if request.session.invalidated:
            for session_id in request.session.invalidated:
                self.redis.delete(self._redis_key(session_id))

            if not request.session.should_save():
                response.delete_cookie(self.cookie_name)

        # Check to see if the session has been marked to be saved, generally
        # this means that the session data has been modified and thus we need
        # to store the new data.
        if request.session.should_save():
            # Save our session in Redis
            self.redis.setex(
                self._redis_key(request.session.sid),
                self.max_age,
                msgpack.packb(
                    request.session, default=object_encode, use_bin_type=True
                ),
            )

            # Send our session cookie to the client
            # NOTE: The lack of a max_age here. This sends the cookie with:
            #  > Expires: Session
            # This will allow effectively allow the cookie to live indefinitely,
            # as long as the user has interacted with the session _before_ the
            # session key expires in redis.
            # Once the session key has expired in redis, the session will be marked
            # as invalid and will not authenticate the account.
            response.set_cookie(
                self.cookie_name,
                self.signer.sign(request.session.sid.encode("utf8")),
                httponly=True,
                secure=request.scheme == "https",
                samesite=b"lax",
            )
            # If there's no user associated with the session, remove the insecure cookie
            # to prevent JavaScript access to it, which can confuse the UI.
            # We cannot access `request.authenticated_userid` at this point in the
            # request lifecycle, so we check the session directly.
            if not request.session.get("auth.userid"):
                response.delete_cookie(USER_ID_INSECURE_COOKIE)


def session_view(view, info):
    if info.options.get("uses_session"):
        # If we're using the session, then we'll just return the original view
        # with a small wrapper around it to ensure that it has a Vary: Cookie
        # header.
        return add_vary("Cookie")(view)
    elif info.exception_only:
        return view
    else:
        # If we're not using the session on this view, then we'll wrap the view
        # with a wrapper that just ensures that the session cannot be used.
        @functools.wraps(view)
        def wrapped(context, request):
            # This whole method is a little bit of an odd duck, we want to make
            # sure that we don't actually *access* request.session, because
            # doing so triggers the machinery to create a new session. So
            # instead we will dig into the request object __dict__ to
            # effectively do the same thing, just without triggering an access
            # on request.session.

            # Save the original session so that we can restore it once the
            # inner views have been called.
            nothing = object()
            original_session = request.__dict__.get("session", nothing)

            # This particular view hasn't been set to allow access to the
            # session, so we'll just assign an InvalidSession to
            # request.session
            request.__dict__["session"] = InvalidSession()

            try:
                # Invoke the real view
                return view(context, request)
            finally:
                # Restore the original session so that things like
                # pyramid_debugtoolbar can access it.
                if original_session is nothing:
                    del request.__dict__["session"]
                else:
                    request.__dict__["session"] = original_session

        return wrapped


session_view.options = {"uses_session"}  # type: ignore


def includeme(config):
    config.set_session_factory(
        SessionFactory(
            config.registry.settings["sessions.secret"],
            config.registry.settings["sessions.url"],
        )
    )

    config.add_view_deriver(session_view, over="csrf_view", under=viewderivers.INGRESS)
