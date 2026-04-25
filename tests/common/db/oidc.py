# SPDX-License-Identifier: Apache-2.0

import factory
import faker

from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGitLabPublisher,
    PendingGooglePublisher,
    PendingSemaphorePublisher,
    SemaphorePublisher,
)

from .accounts import UserFactory
from .base import WarehouseFactory

fake = faker.Faker()


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


class GitLabPublisherFactory(WarehouseFactory):
    class Meta:
        model = GitLabPublisher

    id = factory.Faker("uuid4", cast_to=None)
    project = factory.Faker("pystr", max_chars=12)
    namespace = factory.Faker("pystr", max_chars=12)
    workflow_filepath = "subfolder/example.yml"
    environment = "production"
    issuer_url = "https://gitlab.com"


class PendingGitLabPublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingGitLabPublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = "fake-nonexistent-project"
    project = factory.Faker("pystr", max_chars=12)
    namespace = factory.Faker("pystr", max_chars=12)
    workflow_filepath = "subfolder/example.yml"
    environment = "production"
    issuer_url = "https://gitlab.com"
    added_by = factory.SubFactory(UserFactory)


class GooglePublisherFactory(WarehouseFactory):
    class Meta:
        model = GooglePublisher

    id = factory.Faker("uuid4", cast_to=None)

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    email = factory.Sequence(lambda _: fake.unique.safe_email())

    sub = factory.Faker("pystr", max_chars=12)


class PendingGooglePublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingGooglePublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = "fake-nonexistent-project"

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    email = factory.Sequence(lambda _: fake.unique.safe_email())

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


class SemaphorePublisherFactory(WarehouseFactory):
    class Meta:
        model = SemaphorePublisher

    id = factory.Faker("uuid4", cast_to=None)
    organization = factory.Faker("pystr", max_chars=12)
    semaphore_organization_id = factory.Faker("uuid4")
    project = factory.Faker("pystr", max_chars=12)
    semaphore_project_id = factory.Faker("uuid4")
    repo_slug = factory.LazyAttribute(
        lambda obj: f"{obj.organization}/{obj.project}-repo"
    )


class PendingSemaphorePublisherFactory(WarehouseFactory):
    class Meta:
        model = PendingSemaphorePublisher

    id = factory.Faker("uuid4", cast_to=None)
    project_name = factory.Faker("pystr", max_chars=12)
    organization = factory.Faker("pystr", max_chars=12)
    semaphore_organization_id = factory.Faker("uuid4")
    project = factory.Faker("pystr", max_chars=12)
    semaphore_project_id = factory.Faker("uuid4")
    repo_slug = factory.LazyAttribute(
        lambda obj: f"{obj.organization}/{obj.project}-repo"
    )
    added_by = factory.SubFactory(UserFactory)
