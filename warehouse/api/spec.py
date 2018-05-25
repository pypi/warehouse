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

from apispec import APISpec

from warehouse.api import schema

hypermedia_spec = APISpec(
    title="Hypermedia API",
    version="0.0.0",
    info=dict(description="A resource based hypermedia API"),
    plugins=["apispec.ext.marshmallow"],
)
hypermedia_spec.definition("project", schema=schema.Project)
hypermedia_spec.definition("release", schema=schema.Release)
hypermedia_spec.definition("journal", schema=schema.Journal)
hypermedia_spec.definition("roles", schema=schema.Role)

hypermedia_spec.add_path(
    path="/projects/",
    operations=dict(
        get=dict(
            description="Return a paginated list of all projects",
            responses={"200": {"schema": {"$ref": "#/definitions/project"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/projects/{name}/",
    operations=dict(
        get=dict(
            description="Return details of a specific project",
            responses={"200": {"schema": {"$ref": "#/definitions/project"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/projects/{name}/releases/",
    operations=dict(
        get=dict(
            description="Return a list of all releases of a project",
            responses={"200": {"schema": {"$ref": "#/definitions/release"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/projects/{name}/releases/{version}/",
    operations=dict(
        get=dict(
            decription="Return a single version of a project",
            responses={"200": {"schema": {"$ref": "#/definitions/release"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/projects/{name}/releases/{version}/files/",
    operations=dict(
        get=dict(
            decription="Returns files of this version of the project",
            responses={"200": {"schema": {"$ref": "#/definitions/release"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/projects/{name}/roles/",
    operations=dict(
        get=dict(
            description="Return a list of user roles for this project",
            responses={"200": {"schema": {"$ref": "#/definitions/roles"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/journals/",
    operations=dict(
        get=dict(
            description="Return a paginated list of all changes",
            responses={"200": {"schema": {"$ref": "#/definitions/journal"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/journals/latest/",
    operations=dict(
        get=dict(
            description="Return the id of most recent change",
            responses={"200": {"schema": {"$ref": "#/definitions/journal"}}},
        )
    ),
)
hypermedia_spec.add_path(
    path="/users/{user}/projects/",
    operations=dict(
        get=dict(
            description="Return the projects of a specific user",
            responses={"200": {"schema": {"$ref": "#/definitions/project"}}},
        )
    ),
)
