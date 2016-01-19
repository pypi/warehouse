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

import alembic.config
import sqlalchemy
import venusian
import zope.sqlalchemy

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from warehouse.utils.attrs import make_repr


__all__ = ["includeme", "metadata", "ModelBase"]


# We'll add a basic predicate that won't do anything except allow marking a
# route as read only (or not).
class ReadOnlyPredicate:

    def __init__(self, val, config):
        self.val = val

    def text(self):
        return "read_only = {!r}".format(self.val)

    phash = text

    # This predicate doesn't actually participate in the route selection
    # process, so we'll just always return True.
    def __call__(self, info, request):
        return True


class ModelBase:

    def __repr__(self):
        self.__repr__ = make_repr(*self.__table__.columns.keys(), _self=self)
        return self.__repr__()


# The Global metadata object.
metadata = sqlalchemy.MetaData()


# Base class for models using declarative syntax
ModelBase = declarative_base(cls=ModelBase, metadata=metadata)


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

        venusian.attach(wrapped, callback)

        return wrapped
    return deco


def _configure_alembic(config):
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option("script_location", "warehouse:migrations")
    alembic_cfg.set_main_option(
        "url", config.registry.settings["database.url"],
    )
    return alembic_cfg


def _create_session(request):
    # Create our session
    session = Session(bind=request.registry["sqlalchemy.engine"])

    # Set our transaction to read only if the route has been marked as read
    # only.
    for predicate in request.matched_route.predicates:
        if isinstance(predicate, ReadOnlyPredicate) and predicate.val:
            session.execute(
                """ SET TRANSACTION
                    ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE
                """
            )

    # Register only this particular session with zope.sqlalchemy
    zope.sqlalchemy.register(session, transaction_manager=request.tm)

    # Set a finished callback to close the session at the end of the HTTP
    # request so that the connection is returned to the pool.
    request.add_finished_callback(lambda request: request.db.close())

    # Return our session now that it's created and registered
    return session


def includeme(config):
    # Add a directive to get an alembic configuration.
    config.add_directive("alembic_config", _configure_alembic)

    # Create our SQLAlchemy Engine.
    config.registry["sqlalchemy.engine"] = sqlalchemy.create_engine(
        config.registry.settings["database.url"],
        isolation_level="SERIALIZABLE",
    )

    # Register our request.db property
    config.add_request_method(_create_session, name="db", reify=True)

    # Add a route predicate to mark a route as read only.
    config.add_route_predicate("read_only", ReadOnlyPredicate)
