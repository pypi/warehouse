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

from warehouse.cli import warehouse


@warehouse.group()
def hashing():
    """
    Run Hashing operations for Warehouse data
    """


@hashing.command()
@click.option(
    "-s",
    "--salt",
    prompt=True,
    hide_input=True,
    help="Pass value instead of prompting for salt",
)
@click.option(
    "-b",
    "--batch-size",
    default=10_000,
    show_default=True,
    help="Number of rows to hash at a time",
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
    help="Continue hashing until all rows are hashed",
)
@click.pass_obj
def journal_entry(
    config,
    salt: str,
    batch_size: int,
    sleep_time: int,
    continue_until_done: bool,
):
    """
    Hash `journals.submitted_from` column with salt
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.db import Session

    # This lives in the outer function so we only create a single session per
    # invocation of the CLI command.
    session = Session(bind=config.registry["sqlalchemy.engine"])

    _hash_journal_entries_submitted_from(
        session, salt, batch_size, sleep_time, continue_until_done
    )


def _hash_journal_entries_submitted_from(
    session,
    salt: str,
    batch_size: int,
    sleep_time: int,
    continue_until_done: bool,
) -> None:
    """
    Perform hashing of the `journals.submitted_from` column

    Broken out from the CLI command so that it can be called recursively.
    """
    from sqlalchemy import func, select

    from warehouse.packaging.models import JournalEntry

    # Get rows a batch at a time, only if the row hasn't already been hashed
    # (i.e. the value is shorter than 64 characters)
    unhashed_rows = session.scalars(
        select(JournalEntry)
        .where(func.length(JournalEntry.submitted_from) < 63)
        .order_by(JournalEntry.submitted_date)
        .limit(batch_size)
    ).all()

    # If there are no rows to hash, we're done
    if not unhashed_rows:
        click.echo("No rows to hash. Done!")
        return

    how_many = len(unhashed_rows)

    # Hash the value rows
    click.echo(f"Hashing {how_many} rows...")
    for row in unhashed_rows:
        row.submitted_from = hashlib.sha256(
            (row.submitted_from + salt).encode("utf8")
        ).hexdigest()

    # Update the rows
    session.add_all(unhashed_rows)
    session.commit()

    # If there are more rows to hash, recurse until done
    if continue_until_done and how_many == batch_size:
        click.echo(f"Hashed {batch_size} rows. Sleeping for {sleep_time} second(s)...")
        time.sleep(sleep_time)
        _hash_journal_entries_submitted_from(
            session,
            salt,
            batch_size,
            sleep_time,
            continue_until_done,
        )
    else:
        click.echo(f"Hashed {how_many} rows")
    return
