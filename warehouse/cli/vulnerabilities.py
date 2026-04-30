# SPDX-License-Identifier: Apache-2.0

import random

import click

from warehouse.cli import warehouse


@warehouse.group()
def vulnerabilities():
    """
    Group for vulnerability commands.
    """


@vulnerabilities.command()
@click.option("--count", default=20, help="Number of vulnerability records to create.")
@click.option("--projects", default=10, help="Number of projects to distribute across.")
@click.pass_obj
def generate_random_vulnerabilities(
    config, count, projects
):  # pragma: no cover # dev-only tool
    """
    Generate random VulnerabilityRecords, DEVELOPMENT ONLY

    Creates sample vulnerability data tied to existing releases so the admin
    vulnerabilities UI has something to display. A portion of records use an
    `ECHO-` ID prefix so the bulk-delete flow can be exercised end-to-end.
    """
    import faker

    from sqlalchemy import select

    from warehouse.config import Environment
    from warehouse.db import Session
    from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
    from warehouse.packaging.models import Project

    if not config.registry.settings.get("warehouse.env") == Environment.development:
        raise click.ClickException(
            "This command is only available in development mode."
        )

    session = Session(bind=config.registry["sqlalchemy.engine"])
    fake = faker.Faker()

    selected_projects = session.scalars(select(Project).limit(projects)).unique().all()
    if not selected_projects:
        raise click.ClickException("No projects in the database; run `make initdb`.")

    sources = ["osv", "pysec", "ghsa"]
    created = 0
    for i in range(count):
        project = random.choice(selected_projects)
        project_releases = list(project.releases)
        if not project_releases:
            continue

        # ~25% use the ECHO- prefix so admins can exercise bulk delete.
        if random.random() < 0.25:
            vuln_id = f"ECHO-2024-{i:04d}"
            source = "osv"
        else:
            source = random.choice(sources)
            vuln_id = f"{source.upper()}-2024-{i:04d}"

        sample_size = min(len(project_releases), random.randint(1, 5))
        tied_releases = random.sample(project_releases, sample_size)

        session.add(
            VulnerabilityRecord(
                id=vuln_id,
                source=source,
                link=f"https://example.invalid/{source}/{vuln_id}",
                aliases=[f"CVE-2024-{random.randint(1000, 9999)}"],
                summary=fake.sentence(nb_words=8),
                details=fake.paragraph(nb_sentences=3),
                fixed_in=[f"{random.randint(1, 9)}.{random.randint(0, 9)}.0"],
                releases=tied_releases,
            )
        )
        created += 1

    session.commit()
    click.echo(f"Generated {created} random vulnerability records.")
