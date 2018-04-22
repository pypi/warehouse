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
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    warehouse = config.get_settings().get("warehouse.domain")

    # General Admin pages
    config.add_route("admin.dashboard", "/admin/", domain=warehouse)
    config.add_route("admin.login", "/admin/login/", domain=warehouse)
    config.add_route("admin.logout", "/admin/logout/", domain=warehouse)

    # User related Admin pages
    config.add_route("admin.user.list", "/admin/users/", domain=warehouse)
    config.add_route(
        "admin.user.detail",
        "/admin/users/{user_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.user.delete",
        "/admin/users/{user_id}/delete/",
        domain=warehouse,
    )

    # Project related Admin pages
    config.add_route(
        "admin.project.list",
        "/admin/projects/",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.detail",
        "/admin/projects/{project_name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.releases",
        "/admin/projects/{project_name}/releases/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.release",
        "/admin/projects/{project_name}/release/{version}",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/{version}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.journals",
        "/admin/projects/{project_name}/journals/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.set_upload_limit",
        "/admin/projects/{project_name}/set_upload_limit/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.delete",
        "/admin/projects/{project_name}/delete/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )

    # Journal related Admin pages
    config.add_route(
        "admin.journals.list",
        "/admin/journals/",
        domain=warehouse,
    )

    # Classifier related Admin pages
    config.add_route(
        'admin.classifiers',
        '/admin/classifiers/',
        domain=warehouse,
    )
    config.add_route(
        'admin.classifiers.add',
        '/admin/classifiers/add/',
        domain=warehouse,
    )
    config.add_route(
        'admin.classifiers.deprecate',
        '/admin/classifiers/deprecate/',
        domain=warehouse,
    )

    # Blacklist related Admin pages
    config.add_route(
        "admin.blacklist.list",
        "/admin/blacklist/",
        domain=warehouse,
    )
    config.add_route(
        "admin.blacklist.add",
        "/admin/blacklist/add/",
        domain=warehouse,
    )
    config.add_route(
        "admin.blacklist.remove",
        "/admin/blacklist/remove/",
        domain=warehouse,
    )

    # Email related Admin pages
    config.add_route(
        "admin.emails.list",
        "/admin/emails/",
        domain=warehouse,
    )
    config.add_route(
        "admin.emails.detail",
        "/admin/emails/{email_id}/",
        domain=warehouse,
    )

    # Flags
    config.add_route(
        "admin.flags",
        "/admin/flags/",
        domain=warehouse,
    )
    config.add_route(
        "admin.flags.edit",
        "/admin/flags/edit/",
        domain=warehouse,
    )
