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
    changed provenance), each of the "file added late" cases, and each of the
    project-URL shapes the admin account recovery picker has to rank, owned by
    the `seed-user` account.

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
        ReleaseURLFactory,
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

    # A URL spec is (label, url, verified). Only mark a URL `verify_url` could
    # actually verify: the project's own PyPI page, or anything at or under the
    # publisher's repository or docs domain. A real Trusted Publisher therefore
    # verifies the repository root and every page inside it, so an `/issues`
    # link beside a verified repository is verified too.
    #
    # `urls` is keyed by version. Only the highest-versioned release reaches the
    # admin recovery picker (`Project.releases` is ordered by `_pypi_ordering`,
    # which `_sort_releases` assigns in PEP 440 order, so it is the greatest
    # version rather than the newest upload), so keying by version lets a
    # scenario put URLs on a release the picker will not read.
    #
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
        # The nine below feed the admin account recovery picker at
        # /admin/users/seed-user/account_recovery/initiate/. Expected result:
        # `mixed`, `repo` and `subpaths` are listed first with a green badge on
        # the repository root, then `docs-site`, `pypi-self-link` and
        # `unverified`, then `self-hosted` last with no badge at all. Names break
        # ties within a tier. `nonhttp` and `stale` are absent.
        {
            "name": "seed-recovery-urls-repo",
            "summary": "Dev seed: a verified repository URL",
            "releases": [("1.0.0", 1, [unattested])],
            "urls": {
                "1.0.0": [
                    ("Source", "https://github.com/seed-org/alpha", True),
                    ("Homepage", "https://alpha.example.com", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-mixed",
            "summary": "Dev seed: a verified repository beside unverified URLs",
            "releases": [("1.0.0", 1, [unattested])],
            # `Source` is verified so it outranks `Bug Tracker` despite sorting
            # after it alphabetically. The homepage is on an unrelated domain no
            # publisher could verify.
            "urls": {
                "1.0.0": [
                    ("Source", "https://gitlab.com/seed-org/beta", True),
                    ("Bug Tracker", "https://gitlab.com/other/tracker", False),
                    ("Homepage", "https://beta.example.com", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-subpaths",
            "summary": "Dev seed: verified pages inside a verified repository",
            "releases": [("1.0.0", 1, [unattested])],
            # A Trusted Publisher verifies every subpath of its repository, so
            # all three of these are genuinely verified. Only the root takes a
            # push, so only it may be badged and ranked first. The labels sort
            # the other way round, which is what makes this worth seeding.
            "urls": {
                "1.0.0": [
                    ("Bug Tracker", "https://github.com/seed-org/theta/issues", True),
                    (
                        "Changelog",
                        "https://github.com/seed-org/theta/blob/main/CHANGELOG.md",
                        True,
                    ),
                    ("Repository", "https://github.com/seed-org/theta", True),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-docs-site",
            "summary": "Dev seed: the only verified URL is a Pages docs site",
            "releases": [("1.0.0", 1, [unattested])],
            # A GitHub Trusted Publisher verifies `{owner}.github.io/{repo}`, so
            # this is genuinely proven, but it serves rendered docs and takes no
            # git push. The repository here is on a different owner, so the
            # publisher that verified the docs site would not verify it.
            "urls": {
                "1.0.0": [
                    ("Documentation", "https://seed-org.github.io/delta/", True),
                    ("Source", "https://github.com/another-org/delta", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-self-hosted",
            "summary": "Dev seed: a verified repository on a self-hosted GitLab",
            "releases": [("1.0.0", 1, [unattested])],
            # A self-hosted GitLab is a supported Trusted Publisher issuer, so
            # this really was proven, but the host allowlist does not cover it.
            # The badge is lost rather than wrongly granted; the moderator has
            # to check this one by hand.
            "urls": {
                "1.0.0": [("Source", "https://gitlab.seed-corp.example/eng/iota", True)]
            },
        },
        {
            "name": "seed-recovery-urls-pypi-self-link",
            "summary": "Dev seed: the only verified URL is the PyPI page itself",
            "releases": [("1.0.0", 1, [unattested])],
            # `verify_url` marks a project's own PyPI page verified without any
            # Trusted Publisher, and nobody can push a branch to pypi.org.
            "urls": {
                "1.0.0": [
                    (
                        "PyPI",
                        "https://pypi.org/project/seed-recovery-urls-pypi-self-link/",
                        True,
                    ),
                    ("Source", "https://github.com/seed-org/zeta", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-unverified",
            "summary": "Dev seed: no project URL is verified",
            "releases": [("1.0.0", 1, [unattested])],
            # Lowercase labels are idiomatic in pyproject.toml, and must sort
            # among the capitalized ones rather than after all of them.
            "urls": {
                "1.0.0": [
                    ("repository", "https://github.com/seed-org/gamma", False),
                    ("Homepage", "https://gamma.example.com", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-nonhttp",
            "summary": "Dev seed: project URLs the recovery picker filters out",
            "releases": [("1.0.0", 1, [unattested])],
            "urls": {
                "1.0.0": [
                    ("Repository", "git@github.com:seed-org/eta.git", False),
                    ("Chat", "irc://irc.libera.chat/seed", False),
                ]
            },
        },
        {
            "name": "seed-recovery-urls-stale",
            "summary": "Dev seed: project URLs dropped after the first release",
            "releases": [
                ("1.0.0", 7, [unattested]),
                ("2.0.0", 1, [unattested]),
            ],
            # Only 1.0.0 carries URLs, and the picker reads the latest release,
            # so this project offers the moderator nothing.
            "urls": {
                "1.0.0": [("Source", "https://github.com/seed-org/epsilon", True)]
            },
        },
    ]

    # `file_specs` fails loudly on a miscount via `zip(strict=True)` below, but a
    # mistyped `urls` version key would just silently seed no URLs at all, which
    # is the one thing these scenarios exist to produce. Catch it before any DB
    # work happens.
    for scenario in scenarios:
        declared = {version for version, _, _ in scenario["releases"]}
        if unknown := set(scenario.get("urls", {})) - declared:
            raise click.ClickException(
                f"{scenario['name']}: `urls` names versions with no release: "
                f"{sorted(unknown)}"
            )

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
            for label, url, verified in scenario.get("urls", {}).get(version, []):
                ReleaseURLFactory.create(
                    release=release, name=label, url=url, verified=verified
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
