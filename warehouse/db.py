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

import functools
import logging

import alembic.config
import pyramid_retry
import sqlalchemy
import venusian
import zope.sqlalchemy

from sqlalchemy import event, inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from warehouse.metrics import IMetricsService
from warehouse.utils.attrs import make_repr

__all__ = ["includeme", "metadata", "ModelBase"]


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
class DatabaseNotAvailableError(Exception):
    ...


class ModelBase:
    def __repr__(self):
        inst = inspect(self)
        self.__repr__ = make_repr(
            *[c_attr.key for c_attr in inst.mapper.column_attrs], _self=self
        )
        return self.__repr__()


# The Global metadata object.
metadata = sqlalchemy.MetaData()


# Base class for models using declarative syntax
ModelBase = declarative_base(cls=ModelBase, metadata=metadata)  # type: ignore


class Model(ModelBase):
    __abstract__ = True

    id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
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
    alembic_cfg.set_main_option("url", config.registry.settings["database.url"])
    alembic_cfg.set_section_option("post_write_hooks", "hooks", "black, isort")
    alembic_cfg.set_section_option("post_write_hooks", "black.type", "console_scripts")
    alembic_cfg.set_section_option("post_write_hooks", "black.entrypoint", "black")
    alembic_cfg.set_section_option("post_write_hooks", "isort.type", "console_scripts")
    alembic_cfg.set_section_option("post_write_hooks", "isort.entrypoint", "isort")
    return alembic_cfg


def _create_session(request):
    metrics = request.find_service(IMetricsService, context=None)
    metrics.increment("warehouse.db.session.start")

    # Create our connection, most likely pulling it from the pool of
    # connections
    try:
        connection = request.registry["sqlalchemy.engine"].connect()
    except OperationalError:
        # When we tried to connection to PostgreSQL, our database was not available for
        # some reason. We're going to log it here and then raise our error. Most likely
        # this is a transient error that will go away.
        logger.warning("Got an error connecting to PostgreSQL", exc_info=True)
        metrics.increment("warehouse.db.session.error", tags=["error_in:connecting"])
        raise DatabaseNotAvailableError()

    # Now, create a session from our connection
    session = Session(bind=connection)

    # Register only this particular session with zope.sqlalchemy
    zope.sqlalchemy.register(session, transaction_manager=request.tm)

    # Setup a callback that will ensure that everything is cleaned up at the
    # end of our connection.
    @request.add_finished_callback
    def cleanup(request):
        metrics.increment("warehouse.db.session.finished")
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
    config.registry["sqlalchemy.engine"] = sqlalchemy.create_engine(
        config.registry.settings["database.url"],
        isolation_level=DEFAULT_ISOLATION,
        pool_size=35,
        max_overflow=65,
        pool_timeout=20,
    )

    # Register our request.db property
    config.add_request_method(_create_session, name="db", reify=True)
