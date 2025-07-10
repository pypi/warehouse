# SPDX-License-Identifier: Apache-2.0

import random

import click

from warehouse.cli import warehouse


@warehouse.group()
def observations():
    """
    Group for observation commands.
    """


@observations.command()
@click.pass_obj
def generate_random_observations(config):  # pragma: no cover # dev-only tool
    """
    Generate random Observations, DEVELOPMENT ONLY

    Generates random observations for 10 projects in the database,
    along with any associated Observer models.
    It is only available in development mode, useful for
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    import faker

    from sqlalchemy import select

    from warehouse.accounts.models import User
    from warehouse.config import Environment
    from warehouse.db import Session
    from warehouse.observations.models import ObservationKind
    from warehouse.packaging.models import Project

    # bail early if not in development
    if not config.registry.settings.get("warehouse.env") == Environment.development:
        raise click.ClickException(
            "This command is only available in development mode."
        )

    session = Session(bind=config.registry["sqlalchemy.engine"])

    # A `request`-like object that implements the `db` method
    class MockRequest:
        def __init__(self):
            self.db = session

    request = MockRequest()

    # Get 10 users and project
    users = session.scalars(select(User).limit(10)).unique().all()
    projects = session.scalars(select(Project).limit(10)).all()

    # generate 10 random observations for each project
    for project in projects:
        [
            project.record_observation(
                request=request,
                kind=random.choice(list(ObservationKind)),
                actor=random.choice(users),
                summary="CLI Generated: " + faker.Faker().paragraph(nb_sentences=3),
                payload={"origin": "CLI"},
            )
            for _ in range(10)
        ]
    session.commit()  # Finally, commit the transaction

    click.echo("Generated random observations for 10 projects.")
