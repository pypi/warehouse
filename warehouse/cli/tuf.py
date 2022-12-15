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

import time

from datetime import datetime

import click
import requests

from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.dialects.sqlite import insert
from tuf.api.metadata import Delegations, Metadata

from warehouse.cli import warehouse
from warehouse.packaging.tasks import (
    generate_projects_simple_detail as _generate_projects_simple_detail,
)
from warehouse.packaging.utils import render_simple_detail


@warehouse.group()  # pragma: no-branch
def tuf():
    """
    Manage Warehouse's TUF state.
    """


@tuf.group()
def dev():
    """
    TUF Development purposes commands
    """


def _fetch_succinct_roles(config):
    targets = Metadata.from_file("/var/opt/warehouse/metadata/1.targets.json")
    if targets.signed.delegations is None:
        raise click.ClickException("Failed to get Targets Delegations")

    targets_delegations = targets.signed.delegations
    if targets_delegations.succinct_roles is None:
        raise click.ClickException("Failed to get Targets succinct roles")
    succinct_roles = targets_delegations.succinct_roles

    return succinct_roles


def _rstuf_target_files(path, size, blake2_256_digest, target_role_id):
    return {
        "path": path,
        "info": {
            "length": size,
            "hashes": {"blake2b-256": blake2_256_digest},
        },
        "published": False,
        "action": "ADD",
        "last_update": datetime.now(),
        "targets_role": target_role_id,
    }


def _get_target_role_id(db, table, succinct_roles, path):
    return db.execute(
        table.select().where(
            table.c.rolename == succinct_roles.get_role_for_target(path)
        )
    ).one()[0]


@dev.command()
@click.pass_obj
def import_all(config):
    """
    Collect every PyPI package and add as targets.

    Collect the "paths" for every PyPI package and project details index and add
    as targets. These are packages already in existence, so we'll add all directly
    to RSTUF database as a import process
    """
    # NOTE: RSTUF CLI has an import feature but is not compatible to the Warehouse
    #       SQLAlchemy, as workaround we implemented similar feature here.
    #       https://repository-service-tuf.readthedocs.io/en/v1.0.0a1-draft/guide/general/usage.html#importing-existing-targets  # noqa

    if config.registry.settings["warehouse.env"] != "development":
        raise click.Click("Command allowed for development environment only")

    from warehouse.db import Session
    from warehouse.packaging.models import File, Project

    succinct_roles = _fetch_succinct_roles(config)
    db = Session(bind=config.registry["sqlalchemy.engine"])
    engine = create_engine(config.registry.settings["tuf.database.url"])
    db_metadata = MetaData()
    db_client = engine.connect()
    rstuf_target_files = Table("rstuf_target_files", db_metadata, autoload_with=engine)
    rstuf_target_roles = Table("rstuf_target_roles", db_metadata, autoload_with=engine)
    click.echo("Getting all Projects and generating package indexes")
    rstuf_db_data_indexes = []
    all_projects = db.query(Project).all()
    request = config.task(_generate_projects_simple_detail).get_request()
    request.db = db
    click.echo("Generating simple detail index and adding to RSTUF tables")
    for project in all_projects:
        try:
            blake2_256_digest, path, size = render_simple_detail(
                project, request, store=True
            )
        except OSError:
            continue
        rstuf_db_data_indexes.append(
            _rstuf_target_files(
                path,
                size,
                blake2_256_digest,
                _get_target_role_id(
                    db_client, rstuf_target_roles, succinct_roles, path
                ),
            )
        )

    # FIXME: why do we have duplicated for simple detail indexes?
    db_client.execute(
        insert(rstuf_target_files)
        .values(rstuf_db_data_indexes)
        .on_conflict_do_nothing()
    )
    db.commit()
    click.echo("Getting all Packages")
    files = db.query(File).all()
    click.echo("Importing all packages to RSTUF tables")
    rstuf_db_data_packages = []
    for file in files:
        rstuf_db_data_packages.append(
            _rstuf_target_files(
                file.path,
                file.size,
                file.blake2_256_digest,
                _get_target_role_id(
                    db_client, rstuf_target_roles, succinct_roles, file.path
                ),
            )
        )
    db_client.execute(rstuf_target_files.insert(), rstuf_db_data_packages)
    db.commit()

    # Publish all packages and indexes
    click.echo("Publishing all packages and indexes in TUF metadata")
    publish_targets_url = config.registry.settings["tuf.api.publish.url"]
    publish_all_targets = requests.post(publish_targets_url)

    # Monitoring publish all packages task
    if publish_all_targets.status_code != 202:
        raise click.ClickException(f"Error: {publish_all_targets.text}")

    task_id = publish_all_targets.json()["data"]["task_id"]
    click.echo(f"Publishing packages in TUF metadata. Task id: {task_id}")
    click.echo("Waiting packages and indexes to be published.", nl=False)
    task_url = f"{config.registry.settings['tuf.api.task.url']}?task_id={task_id}"
    while True:
        task_status = requests.get(task_url)
        if task_status.status_code != 200:
            raise click.ClickException(f"Error: {task_status.text}")
        state = task_status.json()["data"]["state"]
        if state == "STARTED" or state == "PENDING":
            click.echo(".", nl=False)
            time.sleep(5)
        elif state == "SUCCESS":
            click.echo("\nAll packages and indexes published.")
            break
        else:
            raise click.ClickException(f"Error: unexpected state {state}")
