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

import factory

from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GooglePublisher,
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGooglePublisher,
)

from .accounts import UserFactory
from .base import WarehouseFactory


class GitHubPublisherFactory(WarehouseFactory):
    class Meta:
        model = GitHubPublisher

    id = factory.Faker("uuid4", cast_to=None)
    repository_name = factory.Faker("pystr", max_chars=12)
    repository_owner = factory.Faker("pystr", max_chars=12)
    repository_owner_id = factory.Faker("pystr", max_chars=12)
    workflow_filename = "example.yml"
    environment = "production"


class PendingGitHubPublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingGitHubPublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = "fake-nonexistent-project"
    repository_name = factory.Faker("pystr", max_chars=12)
    repository_owner = factory.Faker("pystr", max_chars=12)
    repository_owner_id = factory.Faker("pystr", max_chars=12)
    workflow_filename = "example.yml"
    environment = "production"
    added_by = factory.SubFactory(UserFactory)


class GooglePublisherFactory(WarehouseFactory):
    class Meta:
        model = GooglePublisher

    id = factory.Faker("uuid4", cast_to=None)
    email = factory.Faker("safe_email")
    sub = factory.Faker("pystr", max_chars=12)


class PendingGooglePublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingGooglePublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = "fake-nonexistent-project"
    email = factory.Faker("safe_email")
    sub = factory.Faker("pystr", max_chars=12)
    added_by = factory.SubFactory(UserFactory)


class ActiveStatePublisherFactory(WarehouseFactory):
    class Meta:
        model = ActiveStatePublisher

    id = factory.Faker("uuid4", cast_to=None)
    organization = factory.Faker("pystr", max_chars=12)
    activestate_project_name = factory.Faker("pystr", max_chars=12)
    actor = factory.Faker("pystr", max_chars=12)
    actor_id = factory.Faker("uuid4")
    ingredient = factory.Faker("pystr", max_chars=12)


class PendingActiveStatePublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingActiveStatePublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = factory.Faker("pystr", max_chars=12)
    organization = factory.Faker("pystr", max_chars=12)
    activestate_project_name = factory.Faker("pystr", max_chars=12)
    actor = factory.Faker("pystr", max_chars=12)
    actor_id = factory.Faker("uuid4")
    added_by = factory.SubFactory(UserFactory)
    ingredient = factory.Faker("pystr", max_chars=12)
