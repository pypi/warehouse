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

import contextlib

from sqlalchemy import text

from warehouse.cli import warehouse


@contextlib.contextmanager
def alembic_lock(engine, alembic_config):
    with engine.begin() as connection:
        # Attempt to acquire the alembic lock, this will wait until the lock
        # has been acquired allowing multiple commands to wait for each other.
        connection.execute(text("SELECT pg_advisory_lock(hashtext('alembic'))"))

        try:
            # Tell Alembic use our current connection instead of creating it's
            # own.
            alembic_config.attributes["connection"] = connection

            # Yield control back up to let the command itself run.
            yield alembic_config
        finally:
            # Finally we need to release the lock we've acquired.
            connection.execute(text("SELECT pg_advisory_unlock(hashtext('alembic'))"))


@warehouse.group()  # pragma: no branch
def db():
    """
    Manage the Warehouse Database.
    """
