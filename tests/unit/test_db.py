# SPDX-License-Identifier: Apache-2.0

import types

import alembic.config
import psycopg
import pytest
import sqlalchemy
import venusian
import zope.sqlalchemy  # pyright: ignore[reportMissingImports]

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, OperationalError

from warehouse import db
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.db import (
    DEFAULT_ISOLATION,
    DatabaseNotAvailableError,
    ModelBase,
    _configure_alembic,
    _create_session,
    includeme,
    unwrap_dbapi_exceptions,
)

from ..common.db.admin import AdminFlagFactory


def test_model_base_repr(mocker):
    inspected = types.SimpleNamespace(
        mapper=types.SimpleNamespace(column_attrs=[types.SimpleNamespace(key="foo")])
    )
    inspect = mocker.patch.object(db, "inspect", return_value=inspected)

    model = ModelBase()
    model.foo = "bar"

    original_repr = model.__repr__

    assert repr(model) == "ModelBase(foo={})".format(repr("bar"))
    inspect.assert_called_once_with(model)
    assert model.__repr__ is not original_repr
    assert repr(model) == "ModelBase(foo={})".format(repr("bar"))


def test_listens_for(mocker):
    venusian_attach = mocker.patch.object(venusian, "attach", autospec=True)
    event_listen = mocker.patch.object(event, "listen", autospec=True)

    target = mocker.sentinel.target
    identifier = mocker.sentinel.identifier
    args = [mocker.sentinel.arg]
    kwargs = {"my_kwarg": mocker.sentinel.my_kwarg}

    @db.listens_for(target, identifier, *args, **kwargs)
    def handler(config):
        pass

    # Ensure the function is called
    handler(None)

    venusian_attach.assert_called_once_with(handler, mocker.ANY, category="warehouse")

    scanner = types.SimpleNamespace(config=mocker.sentinel.config)
    venusian_attach.call_args.args[1](scanner, None, handler)

    event_listen.assert_called_once_with(
        target, identifier, mocker.ANY, *args, **kwargs
    )


def test_configure_alembic(pyramid_config, mocker):
    config_cls = mocker.patch.object(alembic.config, "Config", autospec=True)
    config_obj = config_cls.return_value

    pyramid_config.registry.settings["database.url"] = mocker.sentinel.database_url

    alembic_config = _configure_alembic(pyramid_config)

    assert alembic_config is config_obj
    assert config_obj.set_main_option.call_args_list == [
        mocker.call("script_location", "warehouse:migrations"),
        mocker.call("url", mocker.sentinel.database_url),
    ]
    assert config_obj.set_section_option.call_args_list == [
        mocker.call("post_write_hooks", "hooks", "ruff_check, ruff_format"),
        mocker.call("post_write_hooks", "ruff_check.type", "exec"),
        mocker.call("post_write_hooks", "ruff_check.executable", "ruff"),
        mocker.call(
            "post_write_hooks",
            "ruff_check.options",
            "check --fix REVISION_SCRIPT_FILENAME",
        ),
        mocker.call("post_write_hooks", "ruff_format.type", "exec"),
        mocker.call("post_write_hooks", "ruff_format.executable", "ruff"),
        mocker.call(
            "post_write_hooks", "ruff_format.options", "format REVISION_SCRIPT_FILENAME"
        ),
    ]


def test_raises_db_available_error(pyramid_services, metrics, mocker):
    def raiser():
        raise OperationalError("foo", {}, psycopg.OperationalError())

    engine = types.SimpleNamespace(connect=raiser)
    request = types.SimpleNamespace(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engine": engine},
    )

    with pytest.raises(DatabaseNotAvailableError):
        _create_session(request)

    assert metrics.increment.call_args_list == [
        mocker.call("warehouse.db.session.start"),
        mocker.call("warehouse.db.session.error", tags=["error_in:connecting"]),
    ]


def test_create_session(mocker, pyramid_services):
    session_obj = types.SimpleNamespace(
        close=mocker.Mock(), get=mocker.Mock(return_value=None)
    )
    session_cls = mocker.patch.object(db, "Session", return_value=session_obj)

    connection = types.SimpleNamespace(close=mocker.Mock())
    engine = types.SimpleNamespace(connect=mocker.Mock(return_value=connection))
    request = types.SimpleNamespace(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engine": engine},
        tm=mocker.sentinel.tm,
        add_finished_callback=mocker.Mock(),
    )

    register = mocker.patch.object(zope.sqlalchemy, "register", autospec=True)

    assert _create_session(request) is session_obj
    session_cls.assert_called_once_with(bind=connection)
    register.assert_called_once_with(
        session_obj, transaction_manager=mocker.sentinel.tm
    )
    request.add_finished_callback.assert_called_once_with(mocker.ANY)
    request.add_finished_callback.call_args.args[0](mocker.sentinel.request2)
    session_obj.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("flag_enabled", "doom_count"),
    [
        (None, 0),
        (False, 0),
        (True, 1),
    ],
)
def test_create_session_read_only_mode(
    flag_enabled, doom_count, mocker, pyramid_services
):
    admin_flag = (
        None if flag_enabled is None else AdminFlagFactory.build(enabled=flag_enabled)
    )
    get = mocker.Mock(return_value=admin_flag)
    session_obj = types.SimpleNamespace(close=mocker.Mock(), get=get)
    mocker.patch.object(db, "Session", return_value=session_obj)
    mocker.patch.object(zope.sqlalchemy, "register", autospec=True)

    connection = types.SimpleNamespace(close=mocker.Mock())
    engine = types.SimpleNamespace(connect=mocker.Mock(return_value=connection))
    request = types.SimpleNamespace(
        find_service=pyramid_services.find_service,
        registry={"sqlalchemy.engine": engine},
        tm=types.SimpleNamespace(doom=mocker.Mock()),
        add_finished_callback=lambda callback: None,
    )

    assert _create_session(request) is session_obj
    get.assert_called_once_with(AdminFlag, AdminFlagValue.READ_ONLY.value)
    assert request.tm.doom.call_count == doom_count


def test_includeme(pyramid_config, mocker):
    create_engine = mocker.patch.object(
        sqlalchemy, "create_engine", autospec=True, return_value=mocker.sentinel.engine
    )
    pyramid_config.registry.settings["database.url"] = mocker.sentinel.database_url
    mocker.spy(pyramid_config, "add_directive")

    includeme(pyramid_config)

    pyramid_config.add_directive.assert_called_once_with(
        "alembic_config", _configure_alembic
    )
    create_engine.assert_called_once_with(
        mocker.sentinel.database_url,
        isolation_level=DEFAULT_ISOLATION,
        pool_size=35,
        max_overflow=65,
        pool_timeout=20,
    )
    assert pyramid_config.registry["sqlalchemy.engine"] is mocker.sentinel.engine


def test_unwrap_dbapi_exceptions():
    original_exception = psycopg.OperationalError()
    sqlalchemy_exception = DBAPIError("foo", {}, original_exception)
    context = types.SimpleNamespace(
        sqlalchemy_exception=sqlalchemy_exception,
        original_exception=original_exception,
    )

    with pytest.raises(psycopg.OperationalError) as e:
        unwrap_dbapi_exceptions(context)

    assert e.value is original_exception


def test_unwrap_dbapi_exceptions_no_op():
    # Not a DBAPIError
    context = types.SimpleNamespace(
        sqlalchemy_exception=OperationalError("foo", {}, None),
        original_exception=None,
    )
    unwrap_dbapi_exceptions(context)

    # No original exception
    context = types.SimpleNamespace(
        sqlalchemy_exception=DBAPIError("foo", {}, None),
        original_exception=None,
    )
    unwrap_dbapi_exceptions(context)
