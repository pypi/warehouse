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
    changed provenance) and each of the "file added late" cases, owned by the
    `seed-user` account.

    Attestation material is fabricated; nothing seeded here will pass cryptographic
    verification.
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    import datetime

    from pypi_attestations import AttestationType
    from sqlalchemy import delete, select

    from warehouse.config import Environment
    from warehouse.constants import MAXIMUM_AGE_FOR_NEW_UPLOADS

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

    # A file spec is (predicate_types, (repository, workflow), days_after_release),
    # with `predicate_types` None for a file carrying no provenance. The named
    # specs below all arrive with their release; `after()` moves one later.
    pypi_a = ([pypi], repo_a, 0)
    slsa_a = ([slsa], repo_a, 0)
    both_a = ([pypi, slsa], repo_a, 0)
    pypi_b = ([pypi], repo_b, 0)
    unattested = (None, None, 0)

    def after(spec, days):
        """The same file, arriving `days` days after its release."""
        predicate_types, repo, _ = spec
        return (predicate_types, repo, days)

    # Each release is (version, days_ago, file_specs). A release's `days_ago`
    # has to exceed its longest delay, or its files would arrive in the future.
    scenarios = [
        {
            "name": "seed-provenance-full-pypi",
            "summary": "Dev seed: all files have PyPI publish attestations",
            "releases": [("1.0.0", 1, [pypi_a] * 3)],
        },
        {
            "name": "seed-provenance-full-slsa",
            "summary": "Dev seed: all files have SLSA provenance attestations",
            "releases": [("1.0.0", 1, [slsa_a] * 3)],
        },
        {
            "name": "seed-provenance-both",
            "summary": "Dev seed: all files have PyPI and SLSA attestations",
            "releases": [("1.0.0", 1, [both_a] * 3)],
        },
        {
            "name": "seed-provenance-partial",
            "summary": "Dev seed: 3 of 5 files have attestations",
            "releases": [("1.0.0", 1, [pypi_a] * 3 + [unattested] * 2)],
        },
        {
            "name": "seed-provenance-inconsistent",
            "summary": "Dev seed: files attested from two different repos",
            "releases": [("1.0.0", 1, [pypi_a] * 2 + [pypi_b] * 2)],
        },
        {
            "name": "seed-provenance-lost",
            "summary": "Dev seed: previous release attested, this one is not",
            "releases": [
                ("1.0.0", 7, [pypi_a] * 2),
                ("2.0.0", 1, [unattested] * 2),
            ],
        },
        {
            "name": "seed-provenance-changed",
            "summary": "Dev seed: repo/workflow changed since previous release",
            "releases": [
                ("1.0.0", 7, [pypi_a] * 2),
                ("2.0.0", 1, [pypi_b] * 2),
            ],
        },
        {
            "name": "seed-late-file-single",
            "summary": "Dev seed: one file added late, one just inside the window",
            # The middle file is the control: the window is compared
            # strictly, so its own final day is still punctual.
            "releases": [
                (
                    "1.0.0",
                    60,
                    [
                        pypi_a,
                        after(pypi_a, MAXIMUM_AGE_FOR_NEW_UPLOADS.days),
                        after(pypi_a, 45),
                    ],
                )
            ],
        },
        {
            "name": "seed-late-file-multiple",
            "summary": "Dev seed: three files added late, at increasing delays",
            "releases": [
                (
                    "1.0.0",
                    100,
                    [
                        pypi_a,
                        after(pypi_a, 20),
                        after(pypi_a, 40),
                        after(pypi_a, 80),
                    ],
                )
            ],
        },
        {
            "name": "seed-late-file-unattested",
            "summary": "Dev seed: an unattested file added late to an attested release",
            "releases": [("1.0.0", 60, [pypi_a] * 2 + [after(unattested, 45)])],
        },
        {
            "name": "seed-late-file-changed-publisher",
            "summary": "Dev seed: a file added late from a different repository",
            # Two warnings at once: the release reads as inconsistent, and the
            # file that made it so is the late one.
            "releases": [("1.0.0", 60, [pypi_a] * 2 + [after(pypi_b, 45)])],
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
            for filename, (predicate_types, repo, days_after) in zip(
                filenames, file_specs, strict=True
            ):
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
                    upload_time=created + datetime.timedelta(days=days_after),
                )
                if predicate_types is not None:
                    repository, workflow = repo
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
