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

import time

import msgpack
import pretend
import pytest
import redis

from pyramid import viewderivers

import warehouse.sessions
import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.sessions import (
    InvalidSession,
    Session,
    SessionFactory,
    includeme,
    session_view,
)
from warehouse.utils import crypto
from warehouse.utils.msgpack import object_encode


class TestInvalidSession:
    @pytest.mark.parametrize(
        "method",
        [
            # IDict methods
            "__contains__",
            "__delitem__",
            "__getitem__",
            "__iter__",
            "__len__",
            "__setitem__",
            "clear",
            "copy",
            "fromkeys",
            "get",
            "items",
            "keys",
            "pop",
            "popitem",
            "setdefault",
            "update",
            "values",
            # ISession methods
            "invalidate",
            "flash",
            "changed",
            "get_csrf_token",
            "peek_flash",
            "new_csrf_token",
            "pop_flash",
            # Our custom methods.
            "should_save",
        ],
    )
    def test_methods_raise(self, method):
        session = InvalidSession()
        with pytest.raises(RuntimeError):
            getattr(session, method)()

    @pytest.mark.parametrize("name", ["created", "new", "sid"])
    def test_propery_raises(self, name):
        session = InvalidSession()
        with pytest.raises(RuntimeError):
            getattr(session, name)


class TestSession:
    @pytest.mark.parametrize(
        ("data", "expected"), [(None, {}), ({}, {}), ({"foo": "bar"}, {"foo": "bar"})]
    )
    def test_create_new(self, monkeypatch, data, expected):
        monkeypatch.setattr(time, "time", lambda: 100)
        monkeypatch.setattr(crypto, "random_token", lambda: "123456")
        session = Session(data)

        assert session == expected
        assert session.sid == "123456"
        assert session.new
        assert session.created == 100
        assert not session.invalidated

    @pytest.mark.parametrize(
        ("data", "expected", "new"),
        [
            (None, {}, True),
            ({}, {}, True),
            ({"foo": "bar"}, {"foo": "bar"}, True),
            (None, {}, False),
            ({}, {}, False),
            ({"foo": "bar"}, {"foo": "bar"}, False),
        ],
    )
    def test_create_with_session_id(self, monkeypatch, data, expected, new):
        monkeypatch.setattr(time, "time", lambda: 100)
        session = Session(data, "wat", new)

        assert session == expected
        assert session.sid == "wat"
        assert session.new is new
        assert session.created == 100
        assert not session.invalidated

    def test_changed_marks_as_changed(self):
        session = Session()
        assert not session._changed
        session.changed()
        assert session._changed

    def test_invalidate(self, monkeypatch):
        session_ids = iter(["123456", "7890"])
        monkeypatch.setattr(crypto, "random_token", lambda: next(session_ids))
        session = Session({"foo": "bar"}, "original id", False)

        assert session == {"foo": "bar"}
        assert session.sid == "original id"
        assert not session.new
        assert not session.invalidated

        session.invalidate()

        assert session == {}
        assert session.sid == "123456"
        assert session.new
        assert session.invalidated == {"original id"}

        session.invalidate()

        assert session == {}
        assert session.sid == "7890"
        assert session.new
        assert session.invalidated == {"original id", "123456"}

    def test_invalidate_empty(self):
        session = Session({"foo": "bar"})
        session.invalidate()
        assert session == {}
        assert session.invalidated == set()

    def test_should_save(self):
        session = Session()
        assert not session.should_save()
        session.changed()
        assert session.should_save()

    def test_reauth_record(self, pyramid_request):
        session = Session()
        assert not session.should_save()
        session.record_auth_timestamp()
        assert session.should_save()

    def test_reauth_unneeded(self):
        session = Session()
        session.record_auth_timestamp()
        assert not session.needs_reauthentication()

    def test_reauth_needed(self):
        session = Session()
        session[session._reauth_timestamp_key] = 0
        assert session.needs_reauthentication()

    def test_reauth_needed_no_value(self):
        session = Session()
        assert session.needs_reauthentication()

    @pytest.mark.parametrize(
        ("data", "method", "args"),
        [
            ({"foo": "bar"}, "__delitem__", ["foo"]),
            ({}, "__setitem__", ["foo", "bar"]),
            ({}, "clear", []),
            ({"foo": "bar"}, "pop", ["foo"]),
            ({"foo": "bar"}, "popitem", []),
            ({}, "setdefault", ["foo", "bar"]),
            ({}, "update", [{"foo": "bar"}]),
        ],
    )
    def test_methods_call_changed(self, data, method, args):
        session = Session(data)
        session.changed = pretend.call_recorder(lambda: None)
        getattr(session, method)(*args)
        assert session.changed.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("queue", "expected"),
        [(None, "_flash_messages"), ("foobar", "_flash_messages.foobar")],
    )
    def test_generate_flash_key(self, queue, expected):
        session = Session()
        assert session._get_flash_queue_key(queue) == expected

    def test_flash_messages(self):
        session = Session()

        assert session.peek_flash() == []
        assert session.peek_flash(queue="foo") == []
        assert session.pop_flash() == []
        assert session.pop_flash(queue="foo") == []

        session.flash("A Flash Message")
        assert session.peek_flash() == ["A Flash Message"]
        assert session.peek_flash(queue="foo") == []

        session.flash("Another Flash Message", queue="foo")
        assert session.peek_flash() == ["A Flash Message"]
        assert session.peek_flash(queue="foo") == ["Another Flash Message"]

        session.flash("A Flash Message")
        assert session.peek_flash() == ["A Flash Message", "A Flash Message"]
        assert session.peek_flash(queue="foo") == ["Another Flash Message"]

        session.flash("A Flash Message", allow_duplicate=True)
        assert session.peek_flash() == [
            "A Flash Message",
            "A Flash Message",
            "A Flash Message",
        ]
        assert session.peek_flash(queue="foo") == ["Another Flash Message"]

        session.flash("A Flash Message", allow_duplicate=False)
        assert session.peek_flash() == [
            "A Flash Message",
            "A Flash Message",
            "A Flash Message",
        ]
        assert session.peek_flash(queue="foo") == ["Another Flash Message"]

        assert session.pop_flash() == [
            "A Flash Message",
            "A Flash Message",
            "A Flash Message",
        ]
        assert session.pop_flash(queue="foo") == ["Another Flash Message"]

        assert session.peek_flash() == []
        assert session.peek_flash(queue="foo") == []
        assert session.pop_flash() == []
        assert session.pop_flash(queue="foo") == []

    def test_csrf_token(self, monkeypatch):
        tokens = iter(["123456", "7890"])
        monkeypatch.setattr(crypto, "random_token", lambda: next(tokens))
        session = Session()

        assert session._csrf_token_key not in session
        assert session.new_csrf_token() == "123456"
        assert session._csrf_token_key in session
        assert session.get_csrf_token() == "123456"
        assert session.new_csrf_token() == "7890"
        assert session._csrf_token_key in session
        assert session.get_csrf_token() == "7890"

    def test_get_csrf_token_empty(self):
        session = Session()
        session.new_csrf_token = pretend.call_recorder(lambda: "123456")

        assert session.get_csrf_token() == "123456"
        assert session.new_csrf_token.calls == [pretend.call()]

    def test_get_totp_secret(self):
        session = Session()
        session[session._totp_secret_key] = b"foobar"

        assert session.get_totp_secret() == b"foobar"

    def test_get_totp_secret_empty(self, monkeypatch):
        generate_totp_secret = pretend.call_recorder(lambda: b"foobar")
        monkeypatch.setattr(otp, "generate_totp_secret", generate_totp_secret)

        session = Session()
        assert session.get_totp_secret() == b"foobar"
        assert session._totp_secret_key in session

    def test_clear_totp_secret(self):
        session = Session()
        session[session._totp_secret_key] = b"foobar"

        session.clear_totp_secret()
        assert not session[session._totp_secret_key]

    def test_get_webauthn_challenge(self):
        session = Session()
        session[session._webauthn_challenge_key] = "not_a_real_challenge"

        assert session.get_webauthn_challenge() == "not_a_real_challenge"

    def test_get_webauthn_challenge_empty(self, monkeypatch):
        generate_webauthn_challenge = pretend.call_recorder(
            lambda: "not_a_real_challenge"
        )
        monkeypatch.setattr(
            webauthn, "generate_webauthn_challenge", generate_webauthn_challenge
        )

        session = Session()
        assert session.get_webauthn_challenge() == "not_a_real_challenge"
        assert session._webauthn_challenge_key in session

    def test_clear_webauthn_challenge(self):
        session = Session()
        session[session._webauthn_challenge_key] = "not_a_real_challenge"

        session.clear_webauthn_challenge()
        assert not session[session._webauthn_challenge_key]


class TestSessionFactory:
    def test_initialize(self, monkeypatch):
        timestamp_signer_obj = pretend.stub()
        timestamp_signer_create = pretend.call_recorder(
            lambda secret, salt: timestamp_signer_obj
        )
        monkeypatch.setattr(crypto, "TimestampSigner", timestamp_signer_create)

        strict_redis_obj = pretend.stub()
        strict_redis_cls = pretend.stub(
            from_url=pretend.call_recorder(lambda url: strict_redis_obj)
        )
        monkeypatch.setattr(redis, "StrictRedis", strict_redis_cls)

        session_factory = SessionFactory("mysecret", "my url")

        assert session_factory.signer is timestamp_signer_obj
        assert session_factory.redis is strict_redis_obj
        assert timestamp_signer_create.calls == [
            pretend.call("mysecret", salt="session")
        ]
        assert strict_redis_cls.from_url.calls == [pretend.call("my url")]

    def test_redis_key(self):
        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        assert (
            session_factory._redis_key("my_session_id")
            == "warehouse/session/data/my_session_id"
        )

    def test_no_current_session(self, pyramid_request):
        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory._process_response = pretend.stub()
        session = session_factory(pyramid_request)

        assert len(pyramid_request.response_callbacks) == 1
        assert (
            pyramid_request.response_callbacks[0] is session_factory._process_response
        )

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    def test_invalid_session_id(self, pyramid_request):
        pyramid_request.cookies["session_id"] = "invalid!"

        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory._process_response = pretend.stub()
        session = session_factory(pyramid_request)

        assert len(pyramid_request.response_callbacks) == 1
        assert (
            pyramid_request.response_callbacks[0] is session_factory._process_response
        )

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    def test_valid_session_id_no_data(self, pyramid_request):
        pyramid_request.cookies["session_id"] = "123456"

        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.signer.unsign = pretend.call_recorder(
            lambda session_id, max_age: b"123456"
        )
        session_factory.redis = pretend.stub(
            get=pretend.call_recorder(lambda key: None)
        )
        session_factory._process_response = pretend.stub()
        session = session_factory(pyramid_request)

        assert len(pyramid_request.response_callbacks) == 1
        assert (
            pyramid_request.response_callbacks[0] is session_factory._process_response
        )

        assert session_factory.signer.unsign.calls == [
            pretend.call("123456", max_age=12 * 60 * 60)
        ]

        assert session_factory.redis.get.calls == [
            pretend.call("warehouse/session/data/123456")
        ]

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    def test_valid_session_id_invalid_data(self, pyramid_request):
        pyramid_request.cookies["session_id"] = "123456"

        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.signer.unsign = pretend.call_recorder(
            lambda session_id, max_age: b"123456"
        )
        session_factory.redis = pretend.stub(
            get=pretend.call_recorder(lambda key: b"invalid data")
        )
        session_factory._process_response = pretend.stub()
        session = session_factory(pyramid_request)

        assert len(pyramid_request.response_callbacks) == 1
        assert (
            pyramid_request.response_callbacks[0] is session_factory._process_response
        )

        assert session_factory.signer.unsign.calls == [
            pretend.call("123456", max_age=12 * 60 * 60)
        ]

        assert session_factory.redis.get.calls == [
            pretend.call("warehouse/session/data/123456")
        ]

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    def test_valid_session_id_valid_data(self, monkeypatch, pyramid_request):
        msgpack_unpackb = pretend.call_recorder(
            lambda bdata, raw, use_list: {"foo": "bar"}
        )
        monkeypatch.setattr(msgpack, "unpackb", msgpack_unpackb)

        pyramid_request.cookies["session_id"] = "123456"

        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.signer.unsign = pretend.call_recorder(
            lambda session_id, max_age: b"123456"
        )
        session_factory.redis = pretend.stub(
            get=pretend.call_recorder(lambda key: b"valid data")
        )
        session_factory._process_response = pretend.stub()
        session = session_factory(pyramid_request)

        assert len(pyramid_request.response_callbacks) == 1
        assert (
            pyramid_request.response_callbacks[0] is session_factory._process_response
        )

        assert session_factory.signer.unsign.calls == [
            pretend.call("123456", max_age=12 * 60 * 60)
        ]

        assert session_factory.redis.get.calls == [
            pretend.call("warehouse/session/data/123456")
        ]

        assert msgpack_unpackb.calls == [
            pretend.call(b"valid data", raw=False, use_list=True)
        ]

        assert isinstance(session, Session)
        assert session == {"foo": "bar"}
        assert session.sid == "123456"
        assert not session.new

    def test_no_save_invalid_session(self, pyramid_request):
        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.redis = pretend.stub()
        pyramid_request.session = InvalidSession()
        response = pretend.stub()
        session_factory._process_response(pyramid_request, response)

    def test_noop_unused_session(self, pyramid_request):
        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.redis = pretend.stub()
        pyramid_request.session.invalidated = set()
        pyramid_request.session.should_save = pretend.call_recorder(lambda: False)
        response = pretend.stub()
        session_factory._process_response(pyramid_request, response)
        assert pyramid_request.session.should_save.calls == [pretend.call()]

    def test_invalidated_deletes_no_save(self, pyramid_request):
        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.redis = pretend.stub(
            delete=pretend.call_recorder(lambda key: None)
        )
        pyramid_request.session.invalidated = ["1", "2"]
        pyramid_request.session.should_save = pretend.call_recorder(lambda: False)
        response = pretend.stub(
            delete_cookie=pretend.call_recorder(lambda cookie: None)
        )
        session_factory._process_response(pyramid_request, response)

        assert session_factory.redis.delete.calls == [
            pretend.call("warehouse/session/data/1"),
            pretend.call("warehouse/session/data/2"),
        ]
        assert pyramid_request.session.should_save.calls == [
            pretend.call(),
            pretend.call(),
        ]
        assert response.delete_cookie.calls == [pretend.call("session_id")]

    def test_invalidated_deletes_save_non_secure(self, monkeypatch, pyramid_request):
        msgpack_packb = pretend.call_recorder(lambda *a, **kw: b"msgpack data")
        monkeypatch.setattr(msgpack, "packb", msgpack_packb)

        session_factory = SessionFactory("mysecret", "redis://redis://localhost:6379/0")
        session_factory.redis = pretend.stub(
            delete=pretend.call_recorder(lambda key: None),
            setex=pretend.call_recorder(lambda key, age, data: None),
        )
        session_factory.signer.sign = pretend.call_recorder(lambda data: "cookie data")
        pyramid_request.scheme = "http"
        pyramid_request.session.sid = "123456"
        pyramid_request.session.invalidated = ["1", "2"]
        pyramid_request.session.should_save = pretend.call_recorder(lambda: True)
        response = pretend.stub(
            set_cookie=pretend.call_recorder(
                lambda cookie, data, max_age, httponly, secure, samesite: None
            )
        )
        session_factory._process_response(pyramid_request, response)

        assert session_factory.redis.delete.calls == [
            pretend.call("warehouse/session/data/1"),
            pretend.call("warehouse/session/data/2"),
        ]
        assert msgpack_packb.calls == [
            pretend.call(
                pyramid_request.session, default=object_encode, use_bin_type=True,
            )
        ]
        assert session_factory.redis.setex.calls == [
            pretend.call("warehouse/session/data/123456", 12 * 60 * 60, b"msgpack data")
        ]
        assert pyramid_request.session.should_save.calls == [
            pretend.call(),
            pretend.call(),
        ]
        assert session_factory.signer.sign.calls == [pretend.call(b"123456")]
        assert response.set_cookie.calls == [
            pretend.call(
                "session_id",
                "cookie data",
                max_age=12 * 60 * 60,
                httponly=True,
                secure=False,
                samesite=b"lax",
            )
        ]


class TestSessionView:
    def test_has_options(self):
        assert set(session_view.options) == {"uses_session"}

    @pytest.mark.parametrize("uses_session", [False, None])
    def test_invalid_session(self, uses_session):
        context = pretend.stub()
        request = pretend.stub(session=pretend.stub())
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            assert isinstance(request.session, InvalidSession)
            return response

        info = pretend.stub(options={}, exception_only=False)
        if uses_session is not None:
            info.options["uses_session"] = uses_session
        derived_view = session_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    def test_valid_session(self, monkeypatch):
        add_vary_cb = pretend.call_recorder(lambda fn: fn)
        add_vary = pretend.call_recorder(lambda vary: add_vary_cb)
        monkeypatch.setattr(warehouse.sessions, "add_vary", add_vary)

        context = pretend.stub()
        request = pretend.stub(session=Session())
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            assert isinstance(request.session, Session)
            return response

        info = pretend.stub(options={"uses_session": True})
        derived_view = session_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert add_vary.calls == [pretend.call("Cookie")]
        assert add_vary_cb.calls == [pretend.call(view)]


def test_includeme(monkeypatch):
    session_factory_obj = pretend.stub()
    session_factory_cls = pretend.call_recorder(lambda secret, url: session_factory_obj)
    monkeypatch.setattr(warehouse.sessions, "SessionFactory", session_factory_cls)

    config = pretend.stub(
        set_session_factory=pretend.call_recorder(lambda factory: None),
        registry=pretend.stub(
            settings={"sessions.secret": "my secret", "sessions.url": "my url"}
        ),
        add_view_deriver=pretend.call_recorder(lambda *a, **kw: None),
    )

    includeme(config)

    assert config.set_session_factory.calls == [pretend.call(session_factory_obj)]
    assert session_factory_cls.calls == [pretend.call("my secret", "my url")]
    assert config.add_view_deriver.calls == [
        pretend.call(session_view, over="csrf_view", under=viewderivers.INGRESS)
    ]
