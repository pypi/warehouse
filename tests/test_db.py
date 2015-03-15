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

import alembic.config
import pretend
import sqlalchemy
import zope.sqlalchemy

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


def test_create_session(monkeypatch):
    session_obj = pretend.stub()
    session_cls = pretend.call_recorder(lambda bind: session_obj)
    monkeypatch.setattr(db, "_Session", session_cls)

    engine = pretend.stub()
    request = pretend.stub(
        registry={"sqlalchemy.engine": engine},
        tm=pretend.stub(),
    )

    register = pretend.call_recorder(lambda session, transaction_manager: None)
    monkeypatch.setattr(zope.sqlalchemy, "register", register)

    assert _create_session(request) is session_obj
    assert session_cls.calls == [pretend.call(bind=engine)]
    assert register.calls == [
        pretend.call(session_obj, transaction_manager=request.tm),
    ]


def test_includeme(monkeypatch):
    class FakeRegistry(dict):
        settings = {"database.url": pretend.stub()}

    engine = pretend.stub()
    create_engine = pretend.call_recorder(lambda url, isolation_level: engine)
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda *a: None),
        registry=FakeRegistry(),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
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
