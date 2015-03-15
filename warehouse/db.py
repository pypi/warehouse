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
import sqlalchemy
import zope.sqlalchemy

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from warehouse.utils.attrs import make_repr


__all__ = ["includeme", "metadata", "ModelBase"]


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
_Session = sessionmaker()


def read_only(info, request):
    # We'll mark this request as read-only, latter on when our session gets
    # created it will look at this and intelligently change the session
    # to a read only serializable transaction to ensure that we get a
    # consistent state between multiple transactions.
    request._db_read_only = True

    # Even though this a route predicate, we're not actually using it for that
    # so we'll just unconditionally return True because we never want this to
    # influence whether or not a route matches.
    return True


def _configure_alembic(config):
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option("script_location", "warehouse:migrations")
    alembic_cfg.set_main_option(
        "url", config.registry.settings["database.url"],
    )
    return alembic_cfg


def _create_session(request):
    # Check to see if this request has been marked read only, if it has then
    # we'll use the read only engine instead of our normal engine. The main
    # difference being that the read only engine will use transactions that
    # are set to SERIALIZABLE READ ONLY DEFERRABLE.
    if getattr(request, "_db_read_only", False):
        engine = request.registry["sqlalchemy.engine.read_only"]
    else:
        engine = request.registry["sqlalchemy.engine"]

    # Create our session
    session = _Session(bind=engine)

    # Register only this particular session with zope.sqlalchemy
    zope.sqlalchemy.register(session, transaction_manager=request.tm)

    # Return our session now that it's created and registered
    return session


def _set_read_only(conn):
    conn.execute("SET TRANSACTION READ ONLY DEFERRABLE")


def includeme(config):
    # Add a directive to get an alembic configuration.
    config.add_directive("alembic_config", _configure_alembic)

    # Create our SQLAlchemy connection pool and engines.
    config.registry["sqlalchemy.engine"] = sqlalchemy.create_engine(
        config.registry.settings["database.url"],
    )
    config.registry["sqlalchemy.engine.read_only"] = sqlalchemy.create_engine(
        config.registry.settings["database.url"],
        isolation_level="SERIALIZABLE",
        # We want to re-use the connection pool from the primary engine.
        pool=config.registry["sqlalchemy.engine"].pool,
    )

    event.listen(
        config.registry["sqlalchemy.engine.read_only"],
        "begin",
        _set_read_only,
    )

    # Register our request.db property
    config.add_request_method(_create_session, name="db", reify=True)
