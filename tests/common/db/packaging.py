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

import factory
import factory.fuzzy

from warehouse.packaging.models import (
    Project, Release, Role, File, JournalEntry,
)

from .accounts import UserFactory
from .base import WarehouseFactory


class ProjectFactory(WarehouseFactory):
    class Meta:
        model = Project

    name = factory.fuzzy.FuzzyText(length=12)


class ReleaseFactory(WarehouseFactory):
    class Meta:
        model = Release

    name = factory.LazyAttribute(lambda o: o.project.name)
    project = factory.SubFactory(ProjectFactory)
    version = factory.Sequence(lambda n: str(n) + ".0")
    _pypi_ordering = factory.Sequence(lambda n: n)

    uploader = factory.SubFactory(UserFactory)


class FileFactory(WarehouseFactory):
    class Meta:
        model = File

    name = factory.LazyAttribute(lambda o: o.release.name)
    release = factory.SubFactory(ReleaseFactory)
    python_version = "source"
    md5_digest = factory.LazyAttribute(
        lambda o: hashlib.md5(o.filename.encode("utf8")).hexdigest()
    )
    sha256_digest = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.filename.encode("utf8")).hexdigest()
    )
    upload_time = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime(2008, 1, 1)
    )
    path = factory.LazyAttribute(
        lambda o: "/".join([
            o.python_version,
            o.release.project.name[0],
            o.release.project.name,
            o.filename,
        ])
    )


class RoleFactory(WarehouseFactory):
    class Meta:
        model = Role

    role_name = "Owner"
    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)


class JournalEntryFactory(WarehouseFactory):
    class Meta:
        model = JournalEntry

    id = factory.Sequence(lambda n: n)
    name = factory.fuzzy.FuzzyText(length=12)
    version = factory.Sequence(lambda n: str(n) + ".0")
    submitted_date = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime(2008, 1, 1)
    )
    submitted_by = factory.SubFactory(UserFactory)
