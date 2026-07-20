# SPDX-License-Identifier: Apache-2.0

import datetime
import hashlib
import random

import factory
import faker
import packaging.utils

from warehouse.observations.models import ObservationKind
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    JournalEntry,
    ProhibitedProjectName,
    Project,
    ProjectSizeLimitRequest,
    Provenance,
    Release,
    Role,
    RoleInvitation,
)
from warehouse.utils import readme

from .accounts import UserFactory
from .base import WarehouseFactory
from .observations import ObserverFactory

fake = faker.Faker()


class ProjectFactory(WarehouseFactory):
    class Meta:
        model = Project

    id = factory.Faker("uuid4", cast_to=None)
    name = factory.Faker("pystr", max_chars=12)
    normalized_name = factory.LazyAttribute(
        lambda o: packaging.utils.canonicalize_name(o.name)
    )


class ProjectSizeLimitRequestFactory(WarehouseFactory):
    class Meta:
        model = ProjectSizeLimitRequest

    id = factory.Faker("uuid4", cast_to=None)
    project = factory.SubFactory(ProjectFactory)
    submitted_by = factory.SubFactory(UserFactory)
    submitted = factory.Faker(
        "date_time_between_dates",
        datetime_start=datetime.datetime(2020, 1, 1),
        datetime_end=datetime.datetime(2022, 1, 1),
    )
    requested_limit = factory.LazyAttribute(
        lambda o: random.randint(1, 100) * (1024**3)
    )
    indexes = "PyPI"
    about_project = factory.Faker("paragraph")
    release_size = factory.Faker("paragraph")
    release_frequency = factory.Faker("paragraph")


class ProjectEventFactory(WarehouseFactory):
    class Meta:
        model = Project.Event

    source = factory.SubFactory(ProjectFactory)


class ProjectObservationFactory(WarehouseFactory):
    class Meta:
        model = Project.Observation

    related = factory.SubFactory(ProjectFactory)
    related_name = factory.LazyAttribute(lambda o: repr(o.related))
    observer = factory.SubFactory(ObserverFactory)

    kind = factory.Faker(
        "random_element", elements=[kind.value[1] for kind in ObservationKind]
    )
    payload = factory.Faker("json")
    summary = factory.Faker("paragraph")


class DescriptionFactory(WarehouseFactory):
    class Meta:
        model = Description

    id = factory.Faker("uuid4", cast_to=None)
    raw = factory.Faker("paragraph")
    html = factory.LazyAttribute(lambda o: readme.render(o.raw))
    rendered_by = factory.LazyAttribute(lambda o: readme.renderer_version())


class ReleaseFactory(WarehouseFactory):
    class Meta:
        model = Release

    id = factory.Faker("uuid4", cast_to=None)
    project = factory.SubFactory(ProjectFactory)
    version = factory.Sequence(lambda n: str(n) + ".0")
    canonical_version = factory.LazyAttribute(
        lambda o: packaging.utils.canonicalize_version(o.version)
    )
    _pypi_ordering = factory.Sequence(lambda n: n)

    uploader = factory.SubFactory(UserFactory)
    description = factory.SubFactory(DescriptionFactory)


class FileFactory(WarehouseFactory):
    class Meta:
        model = File

    release = factory.SubFactory(ReleaseFactory)
    python_version = "source"

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    filename = factory.Sequence(lambda _: fake.unique.file_name())

    md5_digest = factory.LazyAttribute(
        lambda o: hashlib.md5(o.filename.encode("utf8")).hexdigest()
    )
    sha256_digest = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.filename.encode("utf8")).hexdigest()
    )
    blake2_256_digest = factory.LazyAttribute(
        lambda o: hashlib.blake2b(o.filename.encode("utf8"), digest_size=32).hexdigest()
    )
    upload_time = factory.Faker(
        "date_time_between_dates", datetime_start=datetime.datetime(2008, 1, 1)
    )
    path = factory.LazyAttribute(
        lambda o: "/".join(
            [
                o.blake2_256_digest[:2],
                o.blake2_256_digest[2:4],
                o.blake2_256_digest[4:],
                o.filename,
            ]
        )
    )
    size = factory.Faker("pyint")
    packagetype = factory.LazyAttribute(
        lambda _: random.choice(
            [
                "bdist_wheel",
                "sdist",
            ]
        )
    )


class ProvenanceFactory(WarehouseFactory):
    class Meta:
        model = Provenance

    file = factory.SubFactory(FileFactory)
    provenance = factory.Faker("json")


class FileEventFactory(WarehouseFactory):
    class Meta:
        model = File.Event

    source = factory.SubFactory(FileFactory)
    additional = {"publisher_url": None}


class RoleFactory(WarehouseFactory):
    class Meta:
        model = Role

    role_name = "Owner"
    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)


class RoleInvitationFactory(WarehouseFactory):
    class Meta:
        model = RoleInvitation

    invite_status = "pending"
    token = "test_token"
    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)


class DependencyFactory(WarehouseFactory):
    class Meta:
        model = Dependency

    release = factory.SubFactory(ReleaseFactory)
    kind = factory.Faker(
        "random_element", elements=[int(kind) for kind in DependencyKind]
    )
    specifier = factory.Faker("word")


class JournalEntryFactory(WarehouseFactory):
    class Meta:
        model = JournalEntry

    name = factory.Faker("word")
    version = factory.Sequence(lambda n: str(n) + ".0")
    submitted_date = factory.Faker(
        "date_time_between_dates", datetime_start=datetime.datetime(2008, 1, 1)
    )
    submitted_by = factory.SubFactory(UserFactory)


class ProhibitedProjectFactory(WarehouseFactory):
    class Meta:
        model = ProhibitedProjectName

    created = factory.Faker(
        "date_time_between_dates", datetime_start=datetime.datetime(2008, 1, 1)
    )
    name = factory.Faker("pystr", max_chars=12)
    prohibited_by = factory.SubFactory(UserFactory)
