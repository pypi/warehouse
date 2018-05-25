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


def includeme(config):
    # Add a subdomain for the hypermedia api.
    hypermedia = config.get_settings().get("hypermedia.domain")

    config.add_route("api.spec", "/api/", read_only=True, domain=hypermedia)
    config.add_route(
        "api.views.projects",
        "/api/projects/",
        factory="warehouse.packaging.models:ProjectFactory",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.detail",
        "/api/projects/{name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.detail.files",
        "/api/projects/{name}/files/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.releases",
        "/api/projects/{name}/releases/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.releases.detail",
        "/api/projects/{name}/releases/{version}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.releases.files",
        "/api/projects/{name}/releases/{version}/files/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}/{version}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.projects.detail.roles",
        "/api/projects/{name}/roles/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{name}",
        read_only=True,
        domain=hypermedia,
    )
    config.add_route(
        "api.views.journals", "/api/journals/", read_only=True, domain=hypermedia
    )
    # This is the JSON API equivalent of changelog_last_serial()
    config.add_route(
        "api.views.journals.latest",
        "/api/journals/latest/",
        read_only=True,
        domain=hypermedia,
    )
    # This is the JSON API equivalent of user_packages(user)
    config.add_route(
        "api.views.users.details.projects",
        "/api/users/{user}/projects/",
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{user}",
        read_only=True,
        domain=hypermedia,
    )
