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

from unittest import mock

import alembic.config
import pretend
import psycopg2.extensions
import pytest
import sqlalchemy
import venusian
import zope.sqlalchemy

from sqlalchemy import event

from warehouse import db
from warehouse.db import (
    DEFAULT_ISOLATION, ModelBase, includeme, _configure_alembic,
    _create_engine, _create_session, _readonly, _reset,
)


def test_model_base_repr(monkeypatch):
    @pretend.call_recorder
    def inspect(item):
        return pretend.stub(
            mapper=pretend.stub(
                column_attrs=[
                    pretend.stub(key="foo"),
                ],
            ),
        )

    monkeypatch.setattr(db, "inspect", inspect)

    model = ModelBase()
    model.foo = "bar"

    original_repr = model.__repr__

    assert repr(model) == "Base(foo={})".format(repr("bar"))
    assert inspect.calls == [pretend.call(model)]
    assert model.__repr__ is not original_repr
    assert repr(model) == "Base(foo={})".format(repr("bar"))


def test_listens_for(monkeypatch):
    venusian_attach = pretend.call_recorder(lambda fn, cb: None)
    monkeypatch.setattr(venusian, "attach", venusian_attach)

    event_listen = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(event, "listen", event_listen)

    target = pretend.stub()
    identifier = pretend.stub()
    args = [pretend.stub()]
    kwargs = {"my_kwarg": pretend.stub}

    @db.listens_for(target, identifier, *args, **kwargs)
    def handler(config):
        pass

    assert venusian_attach.calls == [pretend.call(handler, mock.ANY)]

    scanner = pretend.stub(config=pretend.stub())
    venusian_attach.calls[0].args[1](scanner, None, handler)

    assert event_listen.calls == [
        pretend.call(target, identifier, mock.ANY, *args, **kwargs),
    ]


def test_configure_alembic(monkeypatch):
    config_obj = pretend.stub(
        set_main_option=pretend.call_recorder(lambda *a: None),
    )

    def config_cls():
        return config_obj

    monkeypatch.setattr(alembic.config, "Config", config_cls)

    config = pretend.stub(
        registry=pretend.stub(settings={"database.url": pretend.stub()}),
    )

    alembic_config = _configure_alembic(config)

    assert alembic_config is config_obj
    assert alembic_config.set_main_option.calls == [
        pretend.call("script_location", "warehouse:migrations"),
        pretend.call("url", config.registry.settings["database.url"]),
    ]


@pytest.mark.parametrize("needs_reset", [True, False, None])
def test_resets_connection(needs_reset):
    dbapi_connection = pretend.stub(
        set_session=pretend.call_recorder(lambda **kw: None),
    )
    connection_record = pretend.stub(info={})

    if needs_reset is not None:
        connection_record.info["warehouse.needs_reset"] = needs_reset

    _reset(dbapi_connection, connection_record)

    if needs_reset:
        assert dbapi_connection.set_session.calls == [
            pretend.call(
                isolation_level=DEFAULT_ISOLATION,
                readonly=False,
                deferrable=False,
            ),
        ]
    else:
        assert dbapi_connection.set_session.calls == []


def test_creates_engine(monkeypatch):
    engine = pretend.stub()
    create_engine = pretend.call_recorder(lambda *a, **kw: engine)
    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)

    listen = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(db.event, "listen", listen)

    url = pretend.stub()

    assert _create_engine(url) is engine
    assert create_engine.calls == [
        pretend.call(
            url,
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
        ),
    ]
    assert listen.calls == [pretend.call(engine, "reset", _reset)]


@pytest.mark.parametrize(
    ("read_only", "tx_status"),
    [
        (True, psycopg2.extensions.TRANSACTION_STATUS_IDLE),
        (True, psycopg2.extensions.TRANSACTION_STATUS_INTRANS),
        (False, psycopg2.extensions.TRANSACTION_STATUS_IDLE),
        (False, psycopg2.extensions.TRANSACTION_STATUS_INTRANS),
    ],
)
def test_create_session(monkeypatch, read_only, tx_status):
    session_obj = pretend.stub(
        close=pretend.call_recorder(lambda: None),
        query=lambda *a: pretend.stub(get=lambda *a: None),
    )
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    connection = pretend.stub(
        connection=pretend.stub(
            get_transaction_status=pretend.call_recorder(lambda: tx_status),
            set_session=pretend.call_recorder(lambda **kw: None),
            rollback=pretend.call_recorder(lambda: None),
        ),
        info={},
        close=pretend.call_recorder(lambda: None),
    )
    engine = pretend.stub(connect=pretend.call_recorder(lambda: connection))
    request = pretend.stub(
        registry={"sqlalchemy.engine": engine},
        tm=pretend.stub(),
        read_only=read_only,
        add_finished_callback=pretend.call_recorder(lambda callback: None),
    )

    request2 = pretend.stub()

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    assert _create_session(request) is session_obj
    assert connection.connection.get_transaction_status.calls == [
        pretend.call(),
    ]
    assert session_cls.calls == [pretend.call(bind=connection)]
    assert register.calls == [
        pretend.call(session_obj, transaction_manager=request.tm),
    ]
    assert request.add_finished_callback.calls == [pretend.call(mock.ANY)]
    request.add_finished_callback.calls[0].args[0](request2)
    assert session_obj.close.calls == [pretend.call()]
    assert connection.close.calls == [pretend.call()]

    if read_only:
        assert connection.info == {"warehouse.needs_reset": True}
        assert connection.connection.set_session.calls == [
            pretend.call(
                isolation_level="SERIALIZABLE",
                readonly=True,
                deferrable=True,
            )
        ]

    if tx_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
        connection.connection.rollback.calls == [pretend.call()]


@pytest.mark.parametrize(
    "admin_flag, is_superuser, doom_calls",
    [
        (None, True, []),
        (None, False, []),
        (pretend.stub(enabled=False), True, []),
        (pretend.stub(enabled=False), False, []),
        (pretend.stub(enabled=True, description='flag description'), True, []),
        (
            pretend.stub(enabled=True, description='flag description'),
            False,
            [pretend.call()],
        ),
    ],
)
def test_create_session_read_only_mode(
        admin_flag, is_superuser, doom_calls, monkeypatch):
    get = pretend.call_recorder(lambda *a: admin_flag)
    session_obj = pretend.stub(
        close=lambda: None,
        query=lambda *a: pretend.stub(get=get),
    )
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    connection = pretend.stub(
        connection=pretend.stub(
            get_transaction_status=lambda: pretend.stub(),
            set_session=lambda **kw: None,
            rollback=lambda: None,
        ),
        info={},
        close=lambda: None,
    )
    engine = pretend.stub(connect=pretend.call_recorder(lambda: connection))
    request = pretend.stub(
        registry={"sqlalchemy.engine": engine},
        tm=pretend.stub(doom=pretend.call_recorder(lambda: None)),
        read_only=False,
        add_finished_callback=lambda callback: None,
        user=pretend.stub(is_superuser=is_superuser),
    )

    assert _create_session(request) is session_obj
    assert get.calls == [pretend.call('read-only')]
    assert request.tm.doom.calls == doom_calls


@pytest.mark.parametrize(
    ("predicates", "expected"),
    [
        ([], False),
        ([db.ReadOnlyPredicate(False, None)], False),
        ([object()], False),
        ([db.ReadOnlyPredicate(True, None)], True),
    ],
)
def test_readonly(predicates, expected):
    request = pretend.stub(matched_route=pretend.stub(predicates=predicates))
    assert _readonly(request) == expected


def test_readonly_no_matched_route():
    request = pretend.stub(matched_route=None)
    assert not _readonly(request)


def test_readonly_predicate():
    assert db.ReadOnlyPredicate(False, None)(pretend.stub(), pretend.stub())
    assert db.ReadOnlyPredicate(True, None)(pretend.stub(), pretend.stub())


def test_includeme(monkeypatch):
    class FakeRegistry(dict):
        settings = {"database.url": pretend.stub()}

    engine = pretend.stub()
    create_engine = pretend.call_recorder(lambda url: engine)
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda *a: None),
        registry=FakeRegistry(),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_route_predicate=pretend.call_recorder(lambda *a, **kw: None),
    )

    monkeypatch.setattr(db, "_create_engine", create_engine)

    includeme(config)

    assert config.add_directive.calls == [
        pretend.call("alembic_config", _configure_alembic),
    ]
    assert create_engine.calls == [
        pretend.call(config.registry.settings["database.url"]),
    ]
    assert config.registry["sqlalchemy.engine"] is engine
    assert config.add_request_method.calls == [
        pretend.call(_create_session, name="db", reify=True),
        pretend.call(_readonly, name="read_only", reify=True),
    ]
    assert config.add_route_predicate.calls == [
        pretend.call("read_only", db.ReadOnlyPredicate),
    ]
