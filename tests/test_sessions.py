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
from warehouse.http import Response
from warehouse.sessions import (
    RedisSessionStore, Session, handle_session, uses_session,
)

import pretend
import pytest


class TestRedisSessionStore:

    def test_redis_key(self):
        store = RedisSessionStore(pretend.stub())
        assert store._redis_key("123456") == "warehouse/session/data/123456"

    def test_generate_key(self):
        random_token = pretend.call_recorder(
            lambda: "EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM"
        )
        store = RedisSessionStore(pretend.stub(), _random_token=random_token)
        assert (store.generate_key()
                == "EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM")

    @pytest.mark.parametrize(("key", "valid"), [
        ("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM", True),
        ("invalid", False),
    ])
    def test_is_valid_key(self, key, valid):
        store = RedisSessionStore(pretend.stub())
        assert store.is_valid_key(key) is valid

    def test_get(self):
        store = RedisSessionStore(
            pretend.stub(
                get=lambda key: b"\x81\xa9user.csrf\xa3wat",
            )
        )
        store.refresh = pretend.call_recorder(lambda session: None)

        session = store.get("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM")

        assert store.refresh.calls == [pretend.call(session)]
        assert not session.new
        assert session == {"user.csrf": "wat"}
        assert session.sid == "EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM"

    def test_get_invalid_session(self):
        store = RedisSessionStore(pretend.stub())
        assert store.get("invalid key").new

    def test_get_no_data_in_redis(self):
        store = RedisSessionStore(pretend.stub(get=lambda key: None))
        assert store.get("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM").new

    def test_get_invalid_data_in_redis(self):
        store = RedisSessionStore(pretend.stub(get=lambda key: b"asdsa"))
        assert store.get("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM").new

    def test_save(self):
        store = RedisSessionStore(
            pretend.stub(
                setex=pretend.call_recorder(lambda key, ttl, data: None),
            ),
        )
        session = Session({"user.csrf": "wat"}, "EUmoN", False)
        store.save(session)

        assert store.redis.setex.calls == [
            pretend.call(
                "warehouse/session/data/EUmoN",
                12 * 60 * 60,
                b"\x81\xa9user.csrf\xa3wat",
            ),
        ]

    def test_delete(self):
        store = RedisSessionStore(
            pretend.stub(delete=pretend.call_recorder(lambda key: None)),
        )
        store.delete(pretend.stub(sid="EUmoN"))

        assert store.redis.delete.calls == [
            pretend.call("warehouse/session/data/EUmoN"),
        ]

    def test_refresh(self):
        store = RedisSessionStore(
            pretend.stub(expire=pretend.call_recorder(lambda key, ttl: None)),
        )
        store.refresh(pretend.stub(sid="EUmoN"))

        assert store.redis.expire.calls == [
            pretend.call("warehouse/session/data/EUmoN", 12 * 60 * 60),
        ]

    def test_cycle(self):
        store = RedisSessionStore(pretend.stub())
        store.delete = pretend.call_recorder(lambda session: None)

        old_session = Session({"user.csrf": "ok"}, "123456", False)
        new_session = store.cycle(old_session)

        assert store.delete.calls == [pretend.call(old_session)]
        assert new_session == old_session
        assert new_session.new
        assert new_session.sid != old_session.sid


class TestSession:

    def test_cycle(self):
        session = Session({}, "123456", False)
        assert not session.cycled
        session.cycle()
        assert session.cycled

    def test_delete(self):
        session = Session({}, "123456", False)
        assert not session.deleted
        session.delete()
        assert session.deleted


class FakeSessionStore:

    def __init__(self):
        self.saved = []
        self.deleted = []
        self.cycled = []

    def new(self):
        return Session({}, "123456", True)

    def get(self, sid):
        return Session({}, sid, False)

    def save(self, session):
        self.saved.append(session)

    def delete(self, session):
        self.deleted.append(session)

    def cycle(self, session):
        self.cycled.append(session)
        return session


class TestHandleSession:

    def test_no_existing_session(self):
        def fn(self, view, app, request, *args, **kwargs):
            return view(app, request, *args, **kwargs)

        def view(app, request):
            request._session["wat"] = "ok"
            return Response()

        app = pretend.stub(session_store=FakeSessionStore())
        request = pretend.stub(cookies={}, is_secure=False)

        response = handle_session(fn)(pretend.stub(), view, app, request)

        assert app.session_store.saved == [
            Session({"wat": "ok"}, "123456", True),
        ]
        assert response.headers.getlist("Set-Cookie") == [
            "session_id=123456; HttpOnly; Path=/",
        ]

    def test_existing_session(self):
        def fn(self, view, app, request, *args, **kwargs):
            return view(app, request, *args, **kwargs)

        def view(app, request):
            request._session["wat"] = "ok"
            return Response()

        app = pretend.stub(session_store=FakeSessionStore())
        request = pretend.stub(cookies={"session_id": "abcd"}, is_secure=False)

        response = handle_session(fn)(pretend.stub(), view, app, request)

        assert app.session_store.saved == [
            Session({"wat": "ok"}, "abcd", False),
        ]
        assert response.headers.getlist("Set-Cookie") == [
            "session_id=abcd; HttpOnly; Path=/",
        ]

    def test_existing_session_no_save(self):
        def fn(self, view, app, request, *args, **kwargs):
            return view(app, request, *args, **kwargs)

        view = lambda app, request: Response()
        app = pretend.stub(session_store=FakeSessionStore())
        request = pretend.stub(cookies={"session_id": "abcd"}, is_secure=False)

        response = handle_session(fn)(pretend.stub(), view, app, request)

        assert app.session_store.saved == []
        assert response.headers.getlist("Set-Cookie") == []

    def test_delete_session(self):
        def fn(self, view, app, request, *args, **kwargs):
            return view(app, request, *args, **kwargs)

        def view(app, request):
            request._session.delete()
            return Response()

        app = pretend.stub(session_store=FakeSessionStore())
        request = pretend.stub(cookies={"session_id": "abcd"}, is_secure=False)

        response = handle_session(fn)(pretend.stub(), view, app, request)

        assert app.session_store.deleted == [
            Session({}, "abcd", False),
        ]
        assert response.headers.getlist("Set-Cookie") == [
            "session_id=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; "
            "Path=/",
        ]

    def test_cycle_session(self):
        def fn(self, view, app, request, *args, **kwargs):
            return view(app, request, *args, **kwargs)

        def view(app, request):
            request._session.cycle()
            return Response()

        app = pretend.stub(session_store=FakeSessionStore())
        request = pretend.stub(cookies={"session_id": "abcd"}, is_secure=False)

        handle_session(fn)(pretend.stub(), view, app, request)

        assert app.session_store.cycled == [Session({}, "abcd", False)]


def test_uses_session():
    view = uses_session(lambda app, request: Response())

    app = pretend.stub()
    request = pretend.stub(_session=pretend.stub())
    response = view(app, request)

    assert request.session is request._session
    assert response.vary.as_set() == {"cookie"}
