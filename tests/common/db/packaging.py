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
import uuid

import factory
import factory.fuzzy
import packaging.utils

from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    JournalEntry,
    ProhibitedProjectName,
    Project,
    ProjectEvent,
    Release,
    Role,
    RoleInvitation,
)
from warehouse.utils import readme

from .accounts import UserFactory
from .base import WarehouseFactory


class ProjectFactory(WarehouseFactory):
    class Meta:
        model = Project

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.fuzzy.FuzzyText(length=12)


class ProjectEventFactory(WarehouseFactory):
    class Meta:
        model = ProjectEvent

    project = factory.SubFactory(ProjectFactory)


class DescriptionFactory(WarehouseFactory):
    class Meta:
        model = Description

    id = factory.LazyFunction(uuid.uuid4)
    raw = factory.fuzzy.FuzzyText(length=100)
    html = factory.LazyAttribute(lambda o: readme.render(o.raw))
    rendered_by = factory.LazyAttribute(lambda o: readme.renderer_version())


class ReleaseFactory(WarehouseFactory):
    class Meta:
        model = Release

    id = factory.LazyFunction(uuid.uuid4)
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
    filename = factory.fuzzy.FuzzyText(length=12)
    md5_digest = factory.LazyAttribute(
        lambda o: hashlib.md5(o.filename.encode("utf8")).hexdigest()
    )
    sha256_digest = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.filename.encode("utf8")).hexdigest()
    )
    blake2_256_digest = factory.LazyAttribute(
        lambda o: hashlib.blake2b(o.filename.encode("utf8"), digest_size=32).hexdigest()
    )
    upload_time = factory.fuzzy.FuzzyNaiveDateTime(datetime.datetime(2008, 1, 1))
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
    kind = factory.fuzzy.FuzzyChoice(int(kind) for kind in DependencyKind)
    specifier = factory.fuzzy.FuzzyText(length=12)


class JournalEntryFactory(WarehouseFactory):
    class Meta:
        model = JournalEntry

    id = factory.Sequence(lambda n: n)
    name = factory.fuzzy.FuzzyText(length=12)
    version = factory.Sequence(lambda n: str(n) + ".0")
    submitted_date = factory.fuzzy.FuzzyNaiveDateTime(datetime.datetime(2008, 1, 1))
    submitted_by = factory.SubFactory(UserFactory)


class ProhibitedProjectFactory(WarehouseFactory):
    class Meta:
        model = ProhibitedProjectName

    created = factory.fuzzy.FuzzyNaiveDateTime(datetime.datetime(2008, 1, 1))
    name = factory.fuzzy.FuzzyText(length=12)
    prohibited_by = factory.SubFactory(UserFactory)
