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
import pytest
import sqlalchemy
import venusian
import zope.sqlalchemy

from sqlalchemy import event

from warehouse import db
from warehouse.db import (
    ModelBase, includeme, _configure_alembic, _create_session,
)


def test_model_base_repr():
    model = ModelBase()
    model.__table__ = pretend.stub(columns={"foo": None})
    model.foo = "bar"

    original_repr = model.__repr__

    assert repr(model) == "Base(foo={})".format(repr("bar"))
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


@pytest.mark.parametrize(
    "predicates",
    [
        [],
        [db.ReadOnlyPredicate(False, None)],
        [object()],
    ],
)
def test_create_session(monkeypatch, predicates):
    session_obj = pretend.stub()
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    engine = pretend.stub()
    request = pretend.stub(
        registry={"sqlalchemy.engine": engine},
        tm=pretend.stub(),
        matched_route=pretend.stub(predicates=predicates),
        add_finished_callback=pretend.call_recorder(lambda callback: None),
    )

    request2 = pretend.stub(
        db=pretend.stub(
            close=pretend.call_recorder(lambda: None),
        ),
    )

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    assert _create_session(request) is session_obj
    assert session_cls.calls == [pretend.call(bind=engine)]
    assert register.calls == [
        pretend.call(session_obj, transaction_manager=request.tm),
    ]
    assert request.add_finished_callback.calls == [pretend.call(mock.ANY)]
    request.add_finished_callback.calls[0].args[0](request2)
    assert request2.db.close.calls == [pretend.call()]


def test_creates_readonly_session(monkeypatch):
    session_obj = pretend.stub(execute=pretend.call_recorder(lambda sql: None))
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "Session", session_cls)

    engine = pretend.stub()
    request = pretend.stub(
        registry={"sqlalchemy.engine": engine},
        tm=pretend.stub(),
        matched_route=pretend.stub(
            predicates=[db.ReadOnlyPredicate(True, None)],
        ),
        add_finished_callback=pretend.call_recorder(lambda callback: None),
    )

    request2 = pretend.stub(
        db=pretend.stub(
            close=pretend.call_recorder(lambda: None),
        ),
    )

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    assert _create_session(request) is session_obj
    assert session_cls.calls == [pretend.call(bind=engine)]
    assert register.calls == [
        pretend.call(session_obj, transaction_manager=request.tm),
    ]
    assert session_obj.execute.calls == [
        pretend.call(
            """ SET TRANSACTION
                    ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE
                """
        ),
    ]
    assert request.add_finished_callback.calls == [pretend.call(mock.ANY)]
    request.add_finished_callback.calls[0].args[0](request2)
    assert request2.db.close.calls == [pretend.call()]


def test_includeme(monkeypatch):
    class FakeRegistry(dict):
        settings = {"database.url": pretend.stub()}

    engine = pretend.stub()
    create_engine = pretend.call_recorder(lambda url, isolation_level: engine)
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda *a: None),
        registry=FakeRegistry(),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_route_predicate=pretend.call_recorder(lambda *a, **kw: None),
    )

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)

    includeme(config)

    assert config.add_directive.calls == [
        pretend.call("alembic_config", _configure_alembic),
    ]
    assert create_engine.calls == [
        pretend.call(
            config.registry.settings["database.url"],
            isolation_level="SERIALIZABLE",
        ),
    ]
    assert config.registry["sqlalchemy.engine"] is engine
    assert config.add_request_method.calls == [
        pretend.call(_create_session, name="db", reify=True),
    ]
    assert config.add_route_predicate.calls == [
        pretend.call("read_only", db.ReadOnlyPredicate),
    ]
