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
import psycopg
import pytest
import sqlalchemy
import venusian
import zope.sqlalchemy

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from warehouse import db
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.db import (
    DEFAULT_ISOLATION,
    DatabaseNotAvailableError,
    ModelBase,
    _configure_alembic,
    _create_session,
    includeme,
)


def test_model_base_repr(monkeypatch):
    @pretend.call_recorder
    def inspect(item):
        return pretend.stub(mapper=pretend.stub(column_attrs=[pretend.stub(key="foo")]))

    monkeypatch.setattr(db, "inspect", inspect)

    model = ModelBase()
    model.foo = "bar"

    original_repr = model.__repr__

    assert repr(model) == "ModelBase(foo={})".format(repr("bar"))
    assert inspect.calls == [pretend.call(model)]
    assert model.__repr__ is not original_repr
    assert repr(model) == "ModelBase(foo={})".format(repr("bar"))


@pytest.mark.parametrize(
    "matched_route,value,expected",
    [
        (None, None, "primary"),
        (True, None, "primary"),
        (True, "primary", "primary"),
        (True, "replica", "replica"),
    ],
)
def test_with_database(matched_route, value, expected):
    route = pretend.stub(predicates=[])
    if value is not None:
        route.predicates.append(db.WithDatabasePredicate(value, pretend.stub()))
    request = pretend.stub(matched_route=route if matched_route else None)

    assert db._select_database(request) == expected


def test_listens_for(monkeypatch):
    venusian_attach = pretend.call_recorder(lambda fn, cb, category=None: None)
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

    assert venusian_attach.calls == [
        pretend.call(handler, mock.ANY, category="warehouse")
    ]

    scanner = pretend.stub(config=pretend.stub())
    venusian_attach.calls[0].args[1](scanner, None, handler)

    assert event_listen.calls == [
        pretend.call(target, identifier, mock.ANY, *args, **kwargs)
    ]


def test_configure_alembic(monkeypatch):
    config_obj = pretend.stub(
        set_main_option=pretend.call_recorder(lambda *a: None),
        set_section_option=pretend.call_recorder(lambda *a: None),
    )

    def config_cls():
        return config_obj

    monkeypatch.setattr(alembic.config, "Config", config_cls)

    config = pretend.stub(
        registry=pretend.stub(settings={"database.primary.url": pretend.stub()})
    )

    alembic_config = _configure_alembic(config)

    assert alembic_config is config_obj
    assert alembic_config.set_main_option.calls == [
        pretend.call("script_location", "warehouse:migrations"),
        pretend.call("url", config.registry.settings["database.primary.url"]),
    ]
    assert alembic_config.set_section_option.calls == [
        pretend.call("post_write_hooks", "hooks", "black, isort"),
        pretend.call("post_write_hooks", "black.type", "console_scripts"),
        pretend.call("post_write_hooks", "black.entrypoint", "black"),
        pretend.call("post_write_hooks", "isort.type", "console_scripts"),
        pretend.call("post_write_hooks", "isort.entrypoint", "isort"),
    ]


def test_raises_db_available_error(monkeypatch, pyramid_services, metrics):
    def raiser():
        raise OperationalError("foo", {}, psycopg.OperationalError())

    def select_database(request):
        return "primary"

    engine = pretend.stub(connect=raiser)
    request = pretend.stub(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engines": {"primary": engine}},
        read_only=False,
    )
    monkeypatch.setattr(db, "_select_database", select_database)

    with pytest.raises(DatabaseNotAvailableError):
        _create_session(request)

    assert metrics.increment.calls == [
        pretend.call("warehouse.db.session.start", tags=["db:primary"]),
        pretend.call(
            "warehouse.db.session.error", tags=["error_in:connecting", "db:primary"]
        ),
    ]


@pytest.mark.parametrize("db_name", ["primary", "replica"])
def test_create_session(monkeypatch, pyramid_services, db_name):
    session_obj = pretend.stub(
        close=pretend.call_recorder(lambda: None),
        get=pretend.call_recorder(lambda *a: None),
    )
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    def select_database(request):
        return db_name

    monkeypatch.setattr(db, "_select_database", select_database)

    connection = pretend.stub(
        connection=pretend.stub(),
        close=pretend.call_recorder(lambda: None),
    )
    engine = pretend.stub(connect=pretend.call_recorder(lambda: connection))
    replica_engine = pretend.stub(connect=pretend.call_recorder(lambda: connection))
    request = pretend.stub(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engines": {"primary": engine, "replica": replica_engine}},
        tm=pretend.stub(),
        add_finished_callback=pretend.call_recorder(lambda callback: None),
    )

    request2 = pretend.stub()

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    assert _create_session(request) is session_obj
    assert session_cls.calls == [pretend.call(bind=connection)]
    assert register.calls == [pretend.call(session_obj, transaction_manager=request.tm)]
    assert request.add_finished_callback.calls == [pretend.call(mock.ANY)]
    request.add_finished_callback.calls[0].args[0](request2)
    assert session_obj.close.calls == [pretend.call()]
    assert connection.close.calls == [pretend.call()]


@pytest.mark.parametrize(
    "admin_flag, is_superuser, doom_calls",
    [
        (None, True, []),
        (None, False, []),
        (pretend.stub(enabled=False), True, []),
        (pretend.stub(enabled=False), False, []),
        (
            pretend.stub(enabled=True, description="flag description"),
            True,
            [pretend.call()],
        ),
        (
            pretend.stub(enabled=True, description="flag description"),
            False,
            [pretend.call()],
        ),
    ],
)
def test_create_session_read_only_mode(
    admin_flag, is_superuser, doom_calls, monkeypatch, pyramid_services
):
    get = pretend.call_recorder(lambda *a: admin_flag)
    session_obj = pretend.stub(close=lambda: None, get=get)
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    def select_database(request):
        return "primary"

    monkeypatch.setattr(db, "_select_database", select_database)

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    connection = pretend.stub(
        connection=pretend.stub(
            set_session=lambda **kw: None,
            rollback=lambda: None,
        ),
        info={},
        close=lambda: None,
    )
    engine = pretend.stub(connect=pretend.call_recorder(lambda: connection))
    request = pretend.stub(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engines": {"primary": engine}},
        tm=pretend.stub(doom=pretend.call_recorder(lambda: None)),
        add_finished_callback=lambda callback: None,
        user=pretend.stub(is_superuser=is_superuser),
    )

    assert _create_session(request) is session_obj
    assert get.calls == [pretend.call(AdminFlag, AdminFlagValue.READ_ONLY.value)]
    assert request.tm.doom.calls == doom_calls


def test_includeme(monkeypatch):
    class FakeRegistry(dict):
        settings = {"database.primary.url": pretend.stub()}

    engine = pretend.stub()
    create_engine = pretend.call_recorder(lambda url, **kw: engine)
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda *a: None),
        registry=FakeRegistry(),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_route_predicate=pretend.call_recorder(lambda *a, **kw: None),
    )
    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)

    includeme(config)

    assert config.add_directive.calls == [
        pretend.call("alembic_config", _configure_alembic)
    ]
    assert create_engine.calls == [
        pretend.call(
            config.registry.settings["database.primary.url"],
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
            logging_name="primary",
        ),
    ]
    assert config.registry["sqlalchemy.engines"]["primary"] is engine
    assert config.registry["sqlalchemy.engines"]["replica"] is engine


def test_includeme_with_replica(monkeypatch):
    class FakeRegistry(dict):
        settings = {
            "database.primary.url": pretend.stub(),
            "database.replica.url": pretend.stub(),
        }

    engine = pretend.stub()
    replica_engine = pretend.stub()
    create_engine = pretend.call_recorder(
        lambda url, **kw: engine if kw["logging_name"] == "primary" else replica_engine
    )
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda *a: None),
        registry=FakeRegistry(),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_route_predicate=pretend.call_recorder(lambda *a, **kw: None),
    )

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)

    includeme(config)

    assert config.add_directive.calls == [
        pretend.call("alembic_config", _configure_alembic)
    ]
    assert create_engine.calls == [
        pretend.call(
            config.registry.settings["database.primary.url"],
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
            logging_name="primary",
        ),
        pretend.call(
            config.registry.settings["database.replica.url"],
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
            logging_name="replica",
        ),
    ]
    assert config.registry["sqlalchemy.engines"]["primary"] is engine
    assert config.registry["sqlalchemy.engines"]["replica"] is replica_engine
