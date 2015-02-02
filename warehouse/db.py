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


__all__ = ["includeme", "metadata"]


metadata = sqlalchemy.MetaData()


def _configure_alembic(config):
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option("script_location", "warehouse:migrations")
    alembic_cfg.set_main_option("url", config.registry["config"].database.url)
    return alembic_cfg


def _db(request):
    conn = request.registry["engine"].connect()

    @request.add_finished_callback
    def close(request):
        conn.close()

    return conn


def includeme(config):
    # Add a directive to get an alembic configuration.
    config.add_directive("alembic_config", _configure_alembic)

    # Create our SQLAlchemy Engine.
    config.registry["engine"] = sqlalchemy.create_engine(
        config.registry["config"].database.url,
    )

    # Register our request.db property
    config.add_request_method(_db, name="db", reify=True)
