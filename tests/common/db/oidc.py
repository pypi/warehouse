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

from warehouse.oidc.models import GitHubProvider, PendingGitHubProvider

from .base import WarehouseFactory


class GitHubProviderFactory(WarehouseFactory):
    class Meta:
        model = GitHubProvider

    id = factory.Faker("uuid4", cast_to=None)
    repository_name = "foo"
    repository_owner = "bar"
    repository_owner_id = 123
    workflow_filename = "example.yml"


class PendingGitHubProviderFactory(WarehouseFactory):
    class Meta:
        model = PendingGitHubProvider

    id = factory.Faker("uuid4", cast_to=None)
    project_name = "fake-nonexistent-project"
    repository_name = "foo"
    repository_owner = "bar"
    repository_owner_id = 123
    workflow_filename = "example.yml"
