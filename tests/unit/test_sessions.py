# SPDX-License-Identifier: Apache-2.0

import time
import types

import markupsafe
import msgpack
import pytest
import redis

from pyramid import viewderivers
from pyramid.interfaces import ISessionFactory
from pyramid.response import Response

import warehouse.sessions

from warehouse.accounts.views import USER_ID_INSECURE_COOKIE
from warehouse.sessions import (
    InvalidSession,
    Session,
    SessionFactory,
    includeme,
    session_view,
)
from warehouse.utils import crypto, otp, webauthn
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
        assert not session.needs_reauthentication(666)

    def test_reauth_needed(self):
        session = Session()
        session[session._reauth_timestamp_key] = 0
        assert session.needs_reauthentication(666)

    def test_reauth_needed_no_value(self):
        session = Session()
        assert session.needs_reauthentication(666)

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
    def test_methods_call_changed(self, mocker, data, method, args):
        session = Session(data)
        mocker.spy(session, "changed")
        getattr(session, method)(*args)
        session.changed.assert_called_once_with()

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
        assert session.peek_flash() == [{"msg": "A Flash Message", "safe": False}]
        assert session.peek_flash(queue="foo") == []

        session.flash("<b>Another</b> Flash Message", queue="foo", safe=True)
        assert session.peek_flash() == [{"msg": "A Flash Message", "safe": False}]
        assert session.peek_flash(queue="foo") == [
            {"msg": "<b>Another</b> Flash Message", "safe": True}
        ]

        session.flash("A Flash Message")
        assert session.peek_flash() == [
            {"msg": "A Flash Message", "safe": False},
            {"msg": "A Flash Message", "safe": False},
        ]
        assert session.peek_flash(queue="foo") == [
            {"msg": "<b>Another</b> Flash Message", "safe": True}
        ]

        session.flash("A Flash Message", allow_duplicate=True)
        assert session.peek_flash() == [
            {"msg": "A Flash Message", "safe": False},
            {"msg": "A Flash Message", "safe": False},
            {"msg": "A Flash Message", "safe": False},
        ]
        assert session.peek_flash(queue="foo") == [
            {"msg": "<b>Another</b> Flash Message", "safe": True}
        ]

        session.flash("A Flash Message", allow_duplicate=False)
        assert session.peek_flash() == [
            {"msg": "A Flash Message", "safe": False},
            {"msg": "A Flash Message", "safe": False},
            {"msg": "A Flash Message", "safe": False},
        ]
        assert session.peek_flash(queue="foo") == [
            {"msg": "<b>Another</b> Flash Message", "safe": True}
        ]

        default_messages = session.pop_flash()
        assert default_messages == [
            "A Flash Message",
            "A Flash Message",
            "A Flash Message",
        ]
        assert [type(m) for m in default_messages] == [str, str, str]
        foo_messages = session.pop_flash(queue="foo")
        assert foo_messages == ["<b>Another</b> Flash Message"]
        assert [type(m) for m in foo_messages] == [markupsafe.Markup]

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

    def test_get_csrf_token_empty(self, mocker):
        session = Session()
        new_csrf_token = mocker.patch.object(
            session, "new_csrf_token", autospec=True, return_value="123456"
        )

        assert session.get_csrf_token() == "123456"
        new_csrf_token.assert_called_once_with()

    def test_get_totp_secret(self):
        session = Session()
        session[session._totp_secret_key] = b"foobar"
        session[session._totp_secret_timestamp_key] = int(time.time()) - 60

        assert session.get_totp_secret() == b"foobar"
        # Using the secret extends its expiry
        assert session[session._totp_secret_timestamp_key] >= int(time.time())

    @pytest.mark.parametrize(
        ("stored", "age"),
        [
            (None, None),
            # Expired
            (b"stale", Session._totp_secret_max_age),
            # Stored before secrets had a timestamp
            (b"stale", None),
        ],
    )
    def test_get_totp_secret_generates(self, monkeypatch, stored, age):
        monkeypatch.setattr(otp, "generate_totp_secret", lambda: b"foobar")

        session = Session()
        session[session._totp_secret_key] = stored
        if age is not None:
            session[session._totp_secret_timestamp_key] = int(time.time()) - age

        assert session.get_totp_secret() == b"foobar"
        assert session.totp_secret_status() == "present"

    def test_get_totp_secret_stable(self):
        session = Session()

        assert session.get_totp_secret() == session.get_totp_secret()

    def test_clear_totp_secret(self):
        session = Session()
        session[session._totp_secret_key] = b"foobar"
        session[session._totp_secret_timestamp_key] = int(time.time())

        session.clear_totp_secret()
        assert not session[session._totp_secret_key]
        assert session._totp_secret_timestamp_key not in session

    @pytest.mark.parametrize(
        ("stored", "age", "expected"),
        [
            (b"foobar", 0, "present"),
            (b"foobar", Session._totp_secret_max_age - 60, "present"),
            (b"foobar", Session._totp_secret_max_age, "expired"),
            (None, 0, "missing"),
        ],
    )
    def test_totp_secret_status(self, stored, age, expected):
        session = Session()
        session[session._totp_secret_key] = stored
        session[session._totp_secret_timestamp_key] = int(time.time()) - age

        assert session.totp_secret_status() == expected

    def test_get_webauthn_challenge(self):
        session = Session()
        session[session._webauthn_challenge_key] = "not_a_real_challenge"

        assert session.get_webauthn_challenge() == "not_a_real_challenge"

    def test_get_webauthn_challenge_empty(self, mocker):
        generate_webauthn_challenge = mocker.patch.object(
            webauthn,
            "generate_webauthn_challenge",
            autospec=True,
            return_value="not_a_real_challenge",
        )

        session = Session()
        assert session.get_webauthn_challenge() == "not_a_real_challenge"
        assert session._webauthn_challenge_key in session
        generate_webauthn_challenge.assert_called_once_with()

    def test_clear_webauthn_challenge(self):
        session = Session()
        session[session._webauthn_challenge_key] = "not_a_real_challenge"

        session.clear_webauthn_challenge()
        assert not session[session._webauthn_challenge_key]

    def test_record_password_timestamp(self):
        session = Session()
        assert not session.should_save()
        session.record_password_timestamp(1646230636)

        assert session[session._password_timestamp_key] == 1646230636
        assert session.should_save()

    @pytest.mark.parametrize(
        ("stored", "current", "expected"),
        [
            (1600000000, 0, True),
            (1600000000, 1600000000, False),
            (0, 1600000000, True),
            (None, 1600000000, False),
        ],
    )
    def test_password_outdated(self, stored, current, expected):
        session = Session()
        session.record_password_timestamp(stored)
        assert session.password_outdated(current) == expected


class TestSessionFactory:
    @pytest.fixture
    def session_factory(self, mocker):
        session_factory = SessionFactory("mysecret", "redis://localhost:6379/0")
        session_factory.redis = mocker.create_autospec(redis.StrictRedis, instance=True)
        return session_factory

    def test_initialize(self):
        session_factory = SessionFactory("mysecret", "redis://myhost:1234/3")

        assert isinstance(session_factory.signer, crypto.TimestampSigner)
        assert session_factory.signer.secret_keys == [b"mysecret"]
        assert session_factory.signer.salt == b"session"
        assert isinstance(session_factory.redis, redis.StrictRedis)
        connection_kwargs = session_factory.redis.connection_pool.connection_kwargs
        assert connection_kwargs["host"] == "myhost"
        assert connection_kwargs["port"] == 1234
        assert connection_kwargs["db"] == 3

    def test_redis_key(self, session_factory):
        assert (
            session_factory._redis_key("my_session_id")
            == "warehouse/session/data/my_session_id"
        )

    def test_no_current_session(self, pyramid_request, session_factory):
        session = session_factory(pyramid_request)

        assert list(pyramid_request.response_callbacks) == [
            session_factory._process_response
        ]

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new
        session_factory.redis.get.assert_not_called()

    def test_invalid_session_id(self, mocker, pyramid_request, session_factory):
        pyramid_request.cookies["session_id"] = "invalid!"
        mocker.spy(session_factory.signer, "unsign")

        session = session_factory(pyramid_request)

        assert list(pyramid_request.response_callbacks) == [
            session_factory._process_response
        ]

        session_factory.signer.unsign.assert_called_once_with(
            "invalid!", max_age=12 * 60 * 60
        )
        session_factory.redis.get.assert_not_called()

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    @pytest.mark.parametrize("bdata", [None, b"invalid data"])
    def test_valid_session_id_no_valid_data(
        self, mocker, pyramid_request, session_factory, bdata
    ):
        cookie = session_factory.signer.sign(b"123456").decode("utf8")
        pyramid_request.cookies["session_id"] = cookie
        mocker.spy(session_factory.signer, "unsign")
        session_factory.redis.get.return_value = bdata

        session = session_factory(pyramid_request)

        assert list(pyramid_request.response_callbacks) == [
            session_factory._process_response
        ]

        session_factory.signer.unsign.assert_called_once_with(
            cookie, max_age=12 * 60 * 60
        )
        session_factory.redis.get.assert_called_once_with(
            "warehouse/session/data/123456"
        )

        assert isinstance(session, Session)
        assert session._sid is None
        assert session.new

    def test_valid_session_id_valid_data(
        self, mocker, pyramid_request, session_factory
    ):
        cookie = session_factory.signer.sign(b"123456").decode("utf8")
        pyramid_request.cookies["session_id"] = cookie
        mocker.spy(session_factory.signer, "unsign")
        bdata = msgpack.packb({"foo": ["bar"]}, use_bin_type=True)
        session_factory.redis.get.return_value = bdata
        unpackb = mocker.spy(msgpack, "unpackb")

        session = session_factory(pyramid_request)

        assert list(pyramid_request.response_callbacks) == [
            session_factory._process_response
        ]

        session_factory.signer.unsign.assert_called_once_with(
            cookie, max_age=12 * 60 * 60
        )
        session_factory.redis.get.assert_called_once_with(
            "warehouse/session/data/123456"
        )
        unpackb.assert_called_once_with(bdata, raw=False, use_list=True)

        assert isinstance(session, Session)
        assert session == {"foo": ["bar"]}
        assert session.sid == "123456"
        assert not session.new

    def test_no_save_invalid_session(self, pyramid_request, session_factory):
        pyramid_request.session = InvalidSession()
        response = Response()

        session_factory._process_response(pyramid_request, response)

        assert session_factory.redis.mock_calls == []
        assert "Set-Cookie" not in response.headers

    def test_noop_unused_session(self, mocker, pyramid_request, session_factory):
        pyramid_request.session = Session()
        mocker.spy(pyramid_request.session, "should_save")
        response = Response()

        session_factory._process_response(pyramid_request, response)

        pyramid_request.session.should_save.assert_called_once_with()
        assert session_factory.redis.mock_calls == []
        assert "Set-Cookie" not in response.headers

    def test_invalidated_deletes_no_save(
        self, mocker, pyramid_request, session_factory
    ):
        pyramid_request.session = Session()
        pyramid_request.session.invalidated = {"1", "2"}
        mocker.spy(pyramid_request.session, "should_save")
        response = Response()

        session_factory._process_response(pyramid_request, response)

        assert sorted(session_factory.redis.delete.call_args_list, key=str) == [
            mocker.call("warehouse/session/data/1"),
            mocker.call("warehouse/session/data/2"),
        ]
        session_factory.redis.setex.assert_not_called()
        assert pyramid_request.session.should_save.call_args_list == [
            mocker.call(),
            mocker.call(),
        ]
        (cookie,) = response.headers.getall("Set-Cookie")
        assert cookie.startswith("session_id=;")

    @pytest.mark.parametrize(
        ("session_data", "deleted_cookies"),
        [
            ({"foo": "bar"}, [USER_ID_INSECURE_COOKIE]),
            ({"auth.userid": "some-user-id"}, []),
        ],
    )
    def test_invalidated_deletes_save_non_secure(
        self, mocker, pyramid_request, session_factory, session_data, deleted_cookies
    ):
        packb = mocker.spy(msgpack, "packb")
        mocker.spy(session_factory.signer, "sign")
        pyramid_request.scheme = "http"
        pyramid_request.session = Session({}, "123456", False)
        pyramid_request.session.update(session_data)
        pyramid_request.session.invalidated = {"1", "2"}
        mocker.spy(pyramid_request.session, "should_save")
        response = mocker.create_autospec(Response, instance=True)

        session_factory._process_response(pyramid_request, response)

        assert sorted(session_factory.redis.delete.call_args_list, key=str) == [
            mocker.call("warehouse/session/data/1"),
            mocker.call("warehouse/session/data/2"),
        ]
        packb.assert_called_once_with(
            pyramid_request.session, default=object_encode, use_bin_type=True
        )
        session_factory.redis.setex.assert_called_once_with(
            "warehouse/session/data/123456", 12 * 60 * 60, packb.spy_return
        )
        assert pyramid_request.session.should_save.call_args_list == [
            mocker.call(),
            mocker.call(),
        ]
        session_factory.signer.sign.assert_called_once_with(b"123456")
        assert response.mock_calls == [
            mocker.call.set_cookie(
                "session_id",
                session_factory.signer.sign.spy_return,
                httponly=True,
                secure=False,
                samesite=b"lax",
            ),
            *[mocker.call.delete_cookie(name) for name in deleted_cookies],
        ]


class TestSessionView:
    def test_has_options(self):
        assert set(session_view.options) == {"uses_session"}

    @pytest.mark.parametrize("has_session", [True, False])
    @pytest.mark.parametrize("uses_session", [False, None])
    def test_invalid_session(self, mocker, pyramid_request, uses_session, has_session):
        context = mocker.sentinel.context
        if not has_session:
            del pyramid_request.session
        original_session = pyramid_request.__dict__.get("session")
        response = mocker.sentinel.response

        def _view(context, request):
            assert isinstance(request.session, InvalidSession)
            return response

        view = mocker.create_autospec(_view, side_effect=_view)

        info = types.SimpleNamespace(options={}, exception_only=False)
        if uses_session is not None:
            info.options["uses_session"] = uses_session
        derived_view = session_view(view, info)

        assert derived_view(context, pyramid_request) is response
        view.assert_called_once_with(context, pyramid_request)
        if has_session:
            assert pyramid_request.__dict__["session"] is original_session
        else:
            assert "session" not in pyramid_request.__dict__

    def test_valid_session(self, mocker, pyramid_request):
        context = mocker.sentinel.context
        pyramid_request.session = Session()
        response = Response()

        def _view(context, request):
            assert isinstance(request.session, Session)
            return response

        view = mocker.create_autospec(_view, side_effect=_view)

        info = types.SimpleNamespace(
            options={"uses_session": True}, exception_only=False
        )
        derived_view = session_view(view, info)

        assert derived_view(context, pyramid_request) is response
        view.assert_called_once_with(context, pyramid_request)
        assert len(pyramid_request.response_callbacks) == 1
        pyramid_request.response_callbacks[0](pyramid_request, response)
        assert response.vary == ("Cookie",)


def test_includeme(mocker, pyramid_config):
    session_factory_cls = mocker.patch.object(
        warehouse.sessions,
        "SessionFactory",
        autospec=True,
        return_value=mocker.sentinel.session_factory,
    )
    pyramid_config.registry.settings["sessions.secret"] = "my secret"
    pyramid_config.registry.settings["sessions.url"] = "my url"
    mocker.spy(pyramid_config, "add_view_deriver")

    includeme(pyramid_config)

    session_factory_cls.assert_called_once_with("my secret", "my url")
    assert (
        pyramid_config.registry.queryUtility(ISessionFactory)
        is mocker.sentinel.session_factory
    )
    pyramid_config.add_view_deriver.assert_called_once_with(
        session_view, over="csrf_view", under=viewderivers.INGRESS
    )
