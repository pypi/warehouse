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
import hashlib
import time

import click

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from warehouse.cli import warehouse


@warehouse.group()
def hashing():
    """
    Run Hashing operations for Warehouse data
    """


@hashing.command()
@click.option(
    "-b",
    "--batch-size",
    default=10_000,
    show_default=True,
    help="Number of rows to associate at a time",
)
@click.option(
    "-st",
    "--sleep-time",
    default=1,
    show_default=True,
    help="Number of seconds to sleep between batches",
)
@click.option(
    "--continue-until-done",
    is_flag=True,
    default=False,
    help="Continue until all rows are complete",
)
@click.pass_obj
def backfill_ipaddrs(
    config,
    batch_size: int,
    sleep_time: int,
    continue_until_done: bool,
):
    """
    Backfill the `ip_addresses.ip_address` column for Events
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.db import Session

    # This lives in the outer function so we only create a single session per
    # invocation of the CLI command.
    session = Session(bind=config.registry["sqlalchemy.engine"])

    salt = config.registry.settings["warehouse.ip_salt"]

    _backfill_ips(session, salt, batch_size, sleep_time, continue_until_done)


def _backfill_ips(
    session,
    salt: str,
    batch_size: int,
    sleep_time: int,
    continue_until_done: bool,
) -> None:
    """
    Create missing IPAddress objects for events that don't have them.

    Broken out from the CLI command so that it can be called recursively.

    TODO: Currently operates on only User events, but should be expanded to
     include Project events and others.
    """
    from warehouse.accounts.models import User
    from warehouse.ip_addresses.models import IpAddress

    # Get rows a batch at a time, only if the row doesn't have an `ip_address_id
    no_ip_obj_rows = session.scalars(
        select(User.Event)
        .where(User.Event.ip_address_id.is_(None))  # type: ignore[attr-defined]
        .order_by(User.Event.time)  # type: ignore[attr-defined]
        .limit(batch_size)
    ).all()

    if not no_ip_obj_rows:
        click.echo("No rows to backfill. Done!")
        return

    how_many = len(no_ip_obj_rows)

    click.echo(f"Backfilling {how_many} rows...")
    for row in no_ip_obj_rows:
        # See if there's already an IPAddress object for this IP.
        # If not, create one.
        try:
            ip_addr = (
                session.query(IpAddress)
                .filter(IpAddress.ip_address == row.ip_address_string)
                .one()
            )
        except NoResultFound:
            ip_addr = IpAddress(  # type: ignore[call-arg]
                ip_address=row.ip_address_string,
                hashed_ip_address=hashlib.sha256(
                    (row.ip_address_string + salt).encode("utf8")
                ).hexdigest(),
            )
        # Associate the IPAddress object with the Event
        row.ip_address_obj = ip_addr
        session.add(ip_addr)

    # Update the rows with any new IPAddress objects
    session.add_all(no_ip_obj_rows)
    session.commit()

    # If there are more rows to backfill, recurse until done
    if continue_until_done and how_many == batch_size:
        click.echo(
            f"Backfilled {batch_size} rows. Sleeping for {sleep_time} second(s)..."
        )
        time.sleep(sleep_time)
        _backfill_ips(
            session,
            salt,
            batch_size,
            sleep_time,
            continue_until_done,
        )
    else:
        click.echo(f"Backfilled {how_many} rows")
    return
