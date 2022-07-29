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

import enum
import functools
import logging

from uuid import UUID

import alembic.config
import psycopg.types.json
import pyramid_retry
import sqlalchemy
import venusian
import zope.sqlalchemy

from pyramid.renderers import JSON
from sqlalchemy import event, func, inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from warehouse.metrics import IMetricsService
from warehouse.utils.attrs import make_repr

__all__ = ["includeme", "metadata", "ModelBase", "Model"]


logger = logging.getLogger(__name__)


DEFAULT_ISOLATION = "READ COMMITTED"


# On the surface this might seem wrong, because retrying a request whose data violates
# the constraints of the database doesn't seem like a useful endeavor. However what
# happens if you have two requests that are trying to insert a row, and that row
# contains a unique, user provided value, you can get into a race condition where both
# requests check the database, see nothing with that value exists, then both attempt to
# insert it. One of the requests will succeed, the other will fail with an
# IntegrityError. Retrying the request that failed will then have it see the object
# created by the other request, and will have it do the appropriate action in that case.
#
# The most common way to run into this, is when submitting a form in the browser, if the
# user clicks twice in rapid succession, the browser will send two almost identical
# requests at basically the same time.
#
# One possible issue that this raises, is that it will slow down "legitimate"
# IntegrityError because they'll have to fail multiple times before they ultimately
# fail. We consider this an acceptable trade off, because deterministic IntegrityError
# should be caught with proper validation prior to submitting records to the database
# anyways.
pyramid_retry.mark_error_retryable(IntegrityError)


# A generic wrapper exception that we'll raise when the database isn't available, we
# use this so we can catch it later and turn it into a generic 5xx error.
class DatabaseNotAvailableError(Exception): ...


# The Global metadata object.
metadata = sqlalchemy.MetaData()


# We'll add a basic predicate that won't do anything except allow marking a
# route to be sent to a specific database.
class WithDatabasePredicate:
    def __init__(self, val, config):
        self.val = val

    def text(self):
        return f"with_database = {self.val!r}"

    phash = text

    # This predicate doesn't actually participate in the route selection
    # process, so we'll just always return True.
    def __call__(self, info, request):
        return True


class ModelBase(DeclarativeBase):
    """Base class for models using declarative syntax."""

    metadata = metadata

    type_annotation_map = {
        # All of our enums prefer the `.value` for database persistence
        # instead of `.name`, which is the default.
        enum.Enum: sqlalchemy.Enum(
            enum.Enum, values_callable=lambda x: [e.value for e in x]
        ),
    }
    def __repr__(self):
        inst = inspect(self)
        self.__repr__ = make_repr(
            *[c_attr.key for c_attr in inst.mapper.column_attrs], _self=self
        )
        return self.__repr__()


class Model(ModelBase):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


# Create our session class here, this will stay stateless as we'll bind the
# engine to each new state we create instead of binding it to the session
# class.
Session = sessionmaker()


def listens_for(target, identifier, *args, **kwargs):
    def deco(wrapped):
        def callback(scanner, _name, wrapped):
            wrapped = functools.partial(wrapped, scanner.config)
            event.listen(target, identifier, wrapped, *args, **kwargs)

        venusian.attach(wrapped, callback, category="warehouse")

        return wrapped

    return deco


def _configure_alembic(config):
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option("script_location", "warehouse:migrations")
    alembic_cfg.set_main_option("url", config.registry.settings["database.primary.url"])
    alembic_cfg.set_section_option("post_write_hooks", "hooks", "black, isort")
    alembic_cfg.set_section_option("post_write_hooks", "black.type", "console_scripts")
    alembic_cfg.set_section_option("post_write_hooks", "black.entrypoint", "black")
    alembic_cfg.set_section_option("post_write_hooks", "isort.type", "console_scripts")
    alembic_cfg.set_section_option("post_write_hooks", "isort.entrypoint", "isort")
    return alembic_cfg


def _select_database(request):
    if request.matched_route is not None:
        for predicate in request.matched_route.predicates:
            if isinstance(predicate, WithDatabasePredicate):
                return predicate.val

    return "primary"


def _create_session(request):
    metrics = request.find_service(IMetricsService, context=None)

    # Create our connection, most likely pulling it from the pool of
    # connections
    db_name = _select_database(request)
    metrics.increment("warehouse.db.session.start", tags=[f"db:{db_name}"])
    try:
        connection = request.registry["sqlalchemy.engines"][db_name].connect()
    except OperationalError:
        # When we tried to connection to PostgreSQL, our database was not available for
        # some reason. We're going to log it here and then raise our error. Most likely
        # this is a transient error that will go away.
        logger.warning("Got an error connecting to PostgreSQL", exc_info=True)
        metrics.increment(
            "warehouse.db.session.error",
            tags=["error_in:connecting", f"db:{db_name}"],
        )
        raise DatabaseNotAvailableError()

    # Now, create a session from our connection
    session = Session(bind=connection)

    # Register only this particular session with zope.sqlalchemy
    zope.sqlalchemy.register(session, transaction_manager=request.tm)

    # Setup a callback that will ensure that everything is cleaned up at the
    # end of our connection.
    @request.add_finished_callback
    def cleanup(request):
        metrics.increment("warehouse.db.session.finished", tags=[f"db:{db_name}"])
        session.close()
        connection.close()

    # Check if we're in read-only mode
    from warehouse.admin.flags import AdminFlag, AdminFlagValue

    flag = session.get(AdminFlag, AdminFlagValue.READ_ONLY.value)
    if flag and flag.enabled:
        request.tm.doom()

    # Return our session now that it's created and registered
    return session


def includeme(config):
    # Add a directive to get an alembic configuration.
    config.add_directive("alembic_config", _configure_alembic)

    # Create our SQLAlchemy Engine.
    config.registry["sqlalchemy.engines"] = {
        "primary": sqlalchemy.create_engine(
            config.registry.settings["database.primary.url"],
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
            logging_name="primary",
        ),
    }

    # If we have a replica url configured, then we'll set our replica engine
    # to connect to that url.
    if replica_url := config.registry.settings.get("database.replica.url"):
        replica_engine = sqlalchemy.create_engine(
            replica_url,
            isolation_level=DEFAULT_ISOLATION,
            pool_size=35,
            max_overflow=65,
            pool_timeout=20,
            logging_name="replica",
        )
    # If we don't have a replica, then we'll just stash our primary engine
    # as our replica engine as well. This will make other logic simpler, as
    # we won't have to conditionalize engine selection on whether a replica
    # exists or not.
    else:
        replica_engine = config.registry["sqlalchemy.engines"]["primary"]
    config.registry["sqlalchemy.engines"]["replica"] = replica_engine

    # Possibly override how to fetch new db sessions from config.settings
    #  Useful in test fixtures
    db_session_factory = config.registry.settings.get(
        "warehouse.db_create_session", _create_session
    )

    # Set a custom JSON serializer for psycopg
    renderer = JSON()
    renderer_factory = renderer(None)

    def serialize_as_json(obj):
        return renderer_factory(obj, {})

    psycopg.types.json.set_json_dumps(serialize_as_json)

    # Register our request.db property
    config.add_request_method(_create_session, name="db", reify=True)

    # Add a route predicate to mark a route as using a specific database.
    config.add_route_predicate("with_database", WithDatabasePredicate)
