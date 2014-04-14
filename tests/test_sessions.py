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

from flask import session
from warehouse.http import Response
from warehouse.sessions import (
    RedisSessionStore, Session, uses_session,
    RedisSessionInterface
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

    def test_get_invalid_session(self, warehouse_app):
        store = RedisSessionStore(pretend.stub())
        assert store.get("invalid key") is None

        request = pretend.stub(cookies={'session': 'invalid key'})
        session_interface = RedisSessionInterface(store)
        assert session_interface.open_session(warehouse_app, request).new

    def test_get_no_data_in_redis(self, warehouse_app):
        store = RedisSessionStore(pretend.stub(get=lambda key: None))
        assert store.get("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM") is None

        request = pretend.stub(cookies={
            'session': "EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM"
        })
        session_interface = RedisSessionInterface(store)
        assert session_interface.open_session(warehouse_app, request).new

    def test_get_invalid_data_in_redis(self, warehouse_app):
        store = RedisSessionStore(pretend.stub(get=lambda key: b"asdsa"))
        assert store.get("EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM") is None
        request = pretend.stub(cookies={
            'session': "EUmoN-Hsp0CFMcULe2KD5c3LjB_otLG-aXZueTkY3DM"
        })
        session_interface = RedisSessionInterface(store)
        assert session_interface.open_session(warehouse_app, request).new

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

    def test_session_modify(self):
        sess = Session()
        assert sess.modified is False
        sess['name'] = 'a new value'
        assert sess.modified is True

    def test_no_existing_session(self, warehouse_app):
        @warehouse_app.route('/view-that-sets-session')
        def view():
            session["wat"] = "ok"
            return ''

        fake_session_store = FakeSessionStore()
        warehouse_app.session_interface = RedisSessionInterface(
            fake_session_store
        )

        with warehouse_app.test_client() as c:
            response = c.get('/view-that-sets-session')
            assert session.modified

        assert response.headers.getlist("Set-Cookie") == [
            "session=123456; HttpOnly; Path=/",
        ]
        assert fake_session_store.saved == [
            Session({"wat": "ok"}, "123456", True),
        ]

    def test_existing_session(self, warehouse_app):
        @warehouse_app.route('/view-that-sets-session')
        def view():
            session["wat"] = "ok"
            return Response()

        fake_session_store = FakeSessionStore()
        warehouse_app.session_interface = RedisSessionInterface(
            fake_session_store
        )

        with warehouse_app.test_client() as c:
            response = c.get(
                '/view-that-sets-session',
                headers={
                    'Cookie': "session=abcd;"
                }
            )

        assert fake_session_store.saved == [
            Session({"wat": "ok"}, "abcd", False),
        ]
        assert response.headers.getlist("Set-Cookie") == [
            "session=abcd; HttpOnly; Path=/",
        ]

    def test_existing_session_no_save(self, warehouse_app):
        @warehouse_app.route('/do-nothing-to-my-session')
        def view():
            return ''

        fake_session_store = FakeSessionStore()
        warehouse_app.session_interface = RedisSessionInterface(
            fake_session_store
        )

        with warehouse_app.test_client() as c:
            response = c.get(
                '/do-nothing-to-my-session',
                headers={
                    'Cookie': "session=abcd;"
                }
            )

        assert fake_session_store.saved == []
        assert response.headers.getlist("Set-Cookie") == []

    def test_delete_session(self, warehouse_app):
        @warehouse_app.route('/delete-thy-session')
        def view():
            session.delete()
            return ''

        fake_session_store = FakeSessionStore()
        warehouse_app.session_interface = RedisSessionInterface(
            fake_session_store
        )

        with warehouse_app.test_client() as c:
            response = c.get(
                '/delete-thy-session',
                headers={
                    'Cookie': "session=abcd;"
                }
            )

        assert fake_session_store.deleted == [
            Session({}, "abcd", False),
        ]
        assert response.headers.getlist("Set-Cookie") == [
            "session=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; "
            "Path=/",
        ]

    def test_cycle_session(self, warehouse_app):
        @warehouse_app.route('/cycle-thy-session')
        def view():
            session.cycle()
            assert session.cycled
            assert session.modified
            return ''

        fake_session_store = FakeSessionStore()
        warehouse_app.session_interface = RedisSessionInterface(
            fake_session_store
        )

        with warehouse_app.test_client() as c:
            c.get(
                '/cycle-thy-session',
                headers={
                    'Cookie': "session=abcd;"
                }
            )
            assert session.cycled

        assert fake_session_store.cycled == [Session({}, "abcd", False)]


def test_uses_session(warehouse_app):
    view = uses_session(lambda: '')

    with warehouse_app.test_request_context():
        response = view()
    assert response.vary.as_set() == {"cookie"}
