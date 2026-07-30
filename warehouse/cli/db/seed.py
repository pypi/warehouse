# SPDX-License-Identifier: Apache-2.0

import click

from warehouse.cli.db import db


@db.command()
@click.pass_obj
def seed(config):  # pragma: no cover # dev-only tool
    """
    Seed the database with recognizable records, DEVELOPMENT ONLY

    Creates a standard set of projects whose releases exhibit each of the
    provenance states surfaced in the UI (full/partial/inconsistent/lost/
    changed provenance), owned by the `seed-user` account.

    Attestation material is fabricated; nothing seeded here will pass cryptographic
    verification.
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    import datetime

    from pypi_attestations import AttestationType
    from sqlalchemy import delete, select

    from warehouse.config import Environment

    # bail early if not in development
    if not config.registry.settings.get("warehouse.env") == Environment.development:
        raise click.ClickException(
            "This command is only available in development mode."
        )

    # The test factories are safe to use here: the dev image installs the
    # tests requirements and the repo (including tests/) is bind-mounted.
    # This mirrors what `warehouse shell` already does in development.
    from tests.common.db import Session
    from tests.common.db.accounts import UserFactory
    from tests.common.db.packaging import (
        FileFactory,
        ProjectFactory,
        ProvenanceFactory,
        ReleaseFactory,
        RoleFactory,
    )
    from warehouse.accounts.models import User
    from warehouse.packaging.models import Filename, Project

    # Binding the scoped session used by the factories makes every
    # `Factory.create()` below use this session. Objects must survive the
    # commit unexpired: the search reindex after_commit hook reads
    # `project.normalized_name`, and an expired instance can't refresh
    # mid-commit.
    session = Session(bind=config.registry["sqlalchemy.engine"], expire_on_commit=False)

    pypi = AttestationType.PYPI_PUBLISH_V1
    slsa = AttestationType.SLSA_PROVENANCE_V1
    repo_a = ("seed-org/alpha", "release.yml")
    repo_b = ("seed-org/beta", "publish.yml")

    # Each release is (version, days_ago, file_specs); each file spec is
    # (predicate_types, (repository, workflow)) or None for no provenance.
    scenarios = [
        {
            "name": "seed-provenance-full-pypi",
            "summary": "Dev seed: all files have PyPI publish attestations",
            "releases": [("1.0.0", 1, [([pypi], repo_a)] * 3)],
        },
        {
            "name": "seed-provenance-full-slsa",
            "summary": "Dev seed: all files have SLSA provenance attestations",
            "releases": [("1.0.0", 1, [([slsa], repo_a)] * 3)],
        },
        {
            "name": "seed-provenance-both",
            "summary": "Dev seed: all files have PyPI and SLSA attestations",
            "releases": [("1.0.0", 1, [([pypi, slsa], repo_a)] * 3)],
        },
        {
            "name": "seed-provenance-partial",
            "summary": "Dev seed: 3 of 5 files have attestations",
            "releases": [("1.0.0", 1, [([pypi], repo_a)] * 3 + [None] * 2)],
        },
        {
            "name": "seed-provenance-inconsistent",
            "summary": "Dev seed: files attested from two different repos",
            "releases": [("1.0.0", 1, [([pypi], repo_a)] * 2 + [([pypi], repo_b)] * 2)],
        },
        {
            "name": "seed-provenance-lost",
            "summary": "Dev seed: previous release attested, this one is not",
            "releases": [
                ("1.0.0", 7, [([pypi], repo_a)] * 2),
                ("2.0.0", 1, [None] * 2),
            ],
        },
        {
            "name": "seed-provenance-changed",
            "summary": "Dev seed: repo/workflow changed since previous release",
            "releases": [
                ("1.0.0", 7, [([pypi], repo_a)] * 2),
                ("2.0.0", 1, [([pypi], repo_b)] * 2),
            ],
        },
    ]

    wheel_tags = [
        "py3-none-any",
        "cp313-cp313-manylinux_2_28_x86_64",
        "cp313-cp313-win_amd64",
        "cp314-cp314-manylinux_2_28_x86_64",
    ]
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    user = session.scalar(select(User).where(User.username == "seed-user"))
    if user is None:
        user = UserFactory.create(
            username="seed-user",
            name="Seed User",
            with_verified_primary_email=True,
        )

    seeded_projects = []
    for scenario in scenarios:
        if session.scalar(select(Project).where(Project.name == scenario["name"])):
            click.echo(f"{scenario['name']}: already exists, skipping")
            continue

        project = ProjectFactory.create(name=scenario["name"])
        RoleFactory.create(project=project, user=user, role_name="Owner")

        for version, days_ago, file_specs in scenario["releases"]:
            created = now - datetime.timedelta(days=days_ago)
            release = ReleaseFactory.create(
                project=project,
                version=version,
                created=created,
                uploader=user,
                summary=scenario["summary"],
            )
            base = scenario["name"].replace("-", "_")
            filenames = [f"{base}-{version}.tar.gz"] + [
                f"{base}-{version}-{tag}.whl"
                for tag in wheel_tags[: len(file_specs) - 1]
            ]
            # Filenames are permanently reserved on upload (see
            # add_filename_to_registry); clear leftover reservations so
            # re-seeding after deleting the seed projects still works.
            session.execute(delete(Filename).where(Filename.filename.in_(filenames)))
            for filename, spec in zip(filenames, file_specs, strict=True):
                file = FileFactory.create(
                    release=release,
                    filename=filename,
                    packagetype=(
                        "sdist" if filename.endswith(".tar.gz") else "bdist_wheel"
                    ),
                    python_version=(
                        "source"
                        if filename.endswith(".tar.gz")
                        else filename.split("-")[-3]
                    ),
                    upload_time=created,
                )
                if spec is not None:
                    predicate_types, (repository, workflow) = spec
                    ProvenanceFactory.create(
                        file=file,
                        predicate_types=predicate_types,
                        repository=repository,
                        workflow=workflow,
                    )
        seeded_projects.append(project)
        click.echo(f"{scenario['name']}: created")

    # The factories expire all instances after every flush; the search
    # reindex after_commit hook needs `normalized_name` already loaded,
    # so warm the seeded projects back up before committing.
    for project in seeded_projects:
        _ = project.normalized_name
    session.commit()
    click.echo("Done. Browse the projects at http://localhost/user/seed-user/")
