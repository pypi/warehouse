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
import re

import factory
import factory.fuzzy

from warehouse.packaging.models import Project, Release, Role, File

from .accounts import UserFactory
from .base import WarehouseFactory


class ProjectFactory(WarehouseFactory):
    class Meta:
        model = Project

    name = factory.fuzzy.FuzzyText(length=12)
    normalized_name = factory.LazyAttribute(
        lambda o: re.sub("[^A-Za-z0-9.]+", "-", o.name).lower()
    )


class ReleaseFactory(WarehouseFactory):
    class Meta:
        model = Release

    project = factory.SubFactory(ProjectFactory)
    version = factory.Sequence(lambda n: str(n) + ".0")
    _pypi_ordering = factory.Sequence(lambda n: n)


class FileFactory(WarehouseFactory):
    class Meta:
        model = File

    release = factory.SubFactory(ReleaseFactory)
    md5_digest = factory.LazyAttribute(
        lambda o: hashlib.md5(o.filename.encode("utf8")).hexdigest()
    )
    upload_time = factory.fuzzy.FuzzyNaiveDateTime(
        datetime.datetime(2008, 1, 1)
    )


class RoleFactory(WarehouseFactory):
    class Meta:
        model = Role

    role_name = "Owner"
    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
