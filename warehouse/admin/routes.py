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
    config.add_route("admin.user.detail", "/admin/users/{user_id}/", domain=warehouse)
    config.add_route(
        "admin.user.add_email", "/admin/users/{user_id}/add_email/", domain=warehouse
    )
    config.add_route(
        "admin.user.delete", "/admin/users/{user_id}/delete/", domain=warehouse
    )
    config.add_route(
        "admin.user.reset_password",
        "/admin/users/{user_id}/reset_password/",
        domain=warehouse,
    )

    # Project related Admin pages
    config.add_route("admin.project.list", "/admin/projects/", domain=warehouse)
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
        "admin.project.set_total_size_limit",
        "/admin/projects/{project_name}/set_total_size_limit/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.add_role",
        "/admin/projects/{project_name}/add_role/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.delete_role",
        "/admin/projects/{project_name}/delete_role/{role_id}/",
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
    config.add_route(
        "admin.project.reindex",
        "/admin/projects/{project_name}/reindex/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )

    # Journal related Admin pages
    config.add_route("admin.journals.list", "/admin/journals/", domain=warehouse)

    # Prohibited Project Name related Admin pages
    config.add_route(
        "admin.prohibited_project_names.list",
        "/admin/prohibited_project_names/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.add",
        "/admin/prohibited_project_names/add/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.remove",
        "/admin/prohibited_project_names/remove/",
        domain=warehouse,
    )

    # Email related Admin pages
    config.add_route("admin.emails.list", "/admin/emails/", domain=warehouse)
    config.add_route("admin.emails.mass", "/admin/emails/mass/", domain=warehouse)
    config.add_route(
        "admin.emails.detail", "/admin/emails/{email_id}/", domain=warehouse
    )

    # Flags
    config.add_route("admin.flags", "/admin/flags/", domain=warehouse)
    config.add_route("admin.flags.edit", "/admin/flags/edit/", domain=warehouse)

    # Malware checks
    config.add_route("admin.checks.list", "/admin/checks/", domain=warehouse)
    config.add_route(
        "admin.checks.detail", "/admin/checks/{check_name}", domain=warehouse
    )
    config.add_route(
        "admin.checks.change_state",
        "/admin/checks/{check_name}/change_state",
        domain=warehouse,
    )
    config.add_route(
        "admin.checks.run_evaluation",
        "/admin/checks/{check_name}/run_evaluation",
        domain=warehouse,
    )
    config.add_route("admin.verdicts.list", "/admin/verdicts/", domain=warehouse)
    config.add_route(
        "admin.verdicts.detail", "/admin/verdicts/{verdict_id}", domain=warehouse
    )
    config.add_route(
        "admin.verdicts.review", "/admin/verdicts/{verdict_id}/review", domain=warehouse
    )
