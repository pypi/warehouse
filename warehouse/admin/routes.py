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

    # Organization related Admin pages
    config.add_route(
        "admin.organization.list", "/admin/organizations/", domain=warehouse
    )
    config.add_route(
        "admin.organization.detail",
        "/admin/organizations/{organization_id}/",
        domain=warehouse,
    )

    config.add_route(
        "admin.organization_application.list",
        "/admin/organization_applications/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.detail",
        "/admin/organization_applications/{organization_application_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.approve",
        "/admin/organization_applications/{organization_application_id}/approve/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.decline",
        "/admin/organization_applications/{organization_application_id}/decline/",
        domain=warehouse,
    )

    # User related Admin pages
    config.add_route("admin.user.list", "/admin/users/", domain=warehouse)
    config.add_route(
        "admin.user.detail",
        "/admin/users/{username}/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.add_email",
        "/admin/users/{username}/add_email/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.delete",
        "/admin/users/{username}/delete/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.reset_password",
        "/admin/users/{username}/reset_password/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.wipe_factors",
        "/admin/users/{username}/wipe_factors/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.prohibited_user_names.bulk_add",
        "/admin/prohibited_user_names/bulk/",
        domain=warehouse,
    )

    # IP Address related Admin pages
    config.add_route("admin.ip_address.list", "/admin/ip-addresses/", domain=warehouse)
    config.add_route(
        "admin.ip_address.detail",
        "/admin/ip-addresses/{ip_address_id}",
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
        "admin.prohibited_project_names.bulk_add",
        "/admin/prohibited_project_names/bulk/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.remove",
        "/admin/prohibited_project_names/remove/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.release",
        "/admin/prohibited_project_names/release/",
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

    # Sponsor related Admin pages
    config.add_route("admin.sponsor.list", "/admin/sponsors/", domain=warehouse)
    config.add_route(
        "admin.sponsor.create", "/admin/sponsors/create/", domain=warehouse
    )
    config.add_route(
        "admin.sponsor.delete", "/admin/sponsors/{sponsor_id}/delete/", domain=warehouse
    )
    config.add_route(
        "admin.sponsor.edit", "/admin/sponsors/{sponsor_id}/", domain=warehouse
    )

    # Banner related Admin pages
    config.add_route("admin.banner.list", "/admin/banners/", domain=warehouse)
    config.add_route("admin.banner.create", "/admin/banners/create/", domain=warehouse)
    config.add_route(
        "admin.banner.delete", "/admin/banners/{banner_id}/delete/", domain=warehouse
    )
    config.add_route(
        "admin.banner.preview", "/admin/banners/{banner_id}/preview/", domain=warehouse
    )
    config.add_route(
        "admin.banner.edit", "/admin/banners/{banner_id}/", domain=warehouse
    )

    # Helpscout Sidebar
    config.add_route("admin.helpscout", "/admin/helpscout/app/", domain=warehouse)
