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

import datetime
import hashlib
import random

import factory
import faker
import packaging.utils

from warehouse.observations.models import ObservationKind
from warehouse.packaging.models import (
    AlternateRepository,
    Dependency,
    DependencyKind,
    Description,
    File,
    JournalEntry,
    ProhibitedProjectName,
    Project,
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
    # TODO: Replace when factory_boy supports `unique`. See https://git.io/JM6kx
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


class AlternateRepositoryFactory(WarehouseFactory):
    class Meta:
        model = AlternateRepository

    name = factory.Faker("word")
    url = factory.Faker("uri")
    description = factory.Faker("text")
    project = factory.SubFactory(ProjectFactory)
