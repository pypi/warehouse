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

import pretend

from warehouse.admin.routes import includeme


def test_includeme():
    warehouse = "w.local"
    config = pretend.stub(
        add_route=pretend.call_recorder(lambda *a, **k: None),
        get_settings=lambda: {"warehouse.domain": warehouse},
    )

    includeme(config)

    assert config.add_route.calls == [
        pretend.call("admin.dashboard", "/admin/", domain=warehouse),
        pretend.call(
            "admin.organization.list", "/admin/organizations/", domain=warehouse
        ),
        pretend.call(
            "admin.organization.detail",
            "/admin/organizations/{organization_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.organization_application.list",
            "/admin/organization_applications/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.organization_application.detail",
            "/admin/organization_applications/{organization_application_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.organization_application.approve",
            "/admin/organization_applications/{organization_application_id}/approve/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.organization_application.decline",
            "/admin/organization_applications/{organization_application_id}/decline/",
            domain=warehouse,
        ),
        pretend.call("admin.user.list", "/admin/users/", domain=warehouse),
        pretend.call(
            "admin.user.detail",
            "/admin/users/{username}/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.user.add_email",
            "/admin/users/{username}/add_email/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.user.delete",
            "/admin/users/{username}/delete/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.user.freeze",
            "/admin/users/{username}/freeze/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.user.reset_password",
            "/admin/users/{username}/reset_password/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.user.wipe_factors",
            "/admin/users/{username}/wipe_factors/",
            domain=warehouse,
            factory="warehouse.accounts.models:UserFactory",
            traverse="/{username}",
        ),
        pretend.call(
            "admin.prohibited_user_names.bulk_add",
            "/admin/prohibited_user_names/bulk/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.macaroon.decode_token", "/admin/token/decode", domain=warehouse
        ),
        pretend.call(
            "admin.macaroon.detail", "/admin/macaroons/{macaroon_id}", domain=warehouse
        ),
        pretend.call(
            "admin.macaroon.delete",
            "/admin/macaroons/{macaroon_id}/delete",
            domain=warehouse,
        ),
        pretend.call("admin.ip_address.list", "/admin/ip-addresses/", domain=warehouse),
        pretend.call(
            "admin.ip_address.detail",
            "/admin/ip-addresses/{ip_address_id}",
            domain=warehouse,
        ),
        pretend.call("admin.project.list", "/admin/projects/", domain=warehouse),
        pretend.call(
            "admin.project.detail",
            "/admin/projects/{project_name}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.releases",
            "/admin/projects/{project_name}/releases/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.release",
            "/admin/projects/{project_name}/release/{version}",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.release.render",
            "/admin/projects/{project_name}/release/{version}/render/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.observations",
            "/admin/projects/{project_name}/observations/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.add_project_observation",
            "/admin/projects/{project_name}/add_project_observation/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.release.observations",
            "/admin/projects/{project_name}/release/{version}/observations/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.release.add_release_observation",
            "/admin/projects/{project_name}/release/{version}/add_release_observation/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}/{version}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.journals",
            "/admin/projects/{project_name}/journals/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.set_upload_limit",
            "/admin/projects/{project_name}/set_upload_limit/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.set_total_size_limit",
            "/admin/projects/{project_name}/set_total_size_limit/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.add_role",
            "/admin/projects/{project_name}/add_role/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.delete_role",
            "/admin/projects/{project_name}/delete_role/{role_id}/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.delete",
            "/admin/projects/{project_name}/delete/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.reindex",
            "/admin/projects/{project_name}/reindex/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call("admin.journals.list", "/admin/journals/", domain=warehouse),
        pretend.call(
            "admin.prohibited_project_names.list",
            "/admin/prohibited_project_names/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.prohibited_project_names.add",
            "/admin/prohibited_project_names/add/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.prohibited_project_names.bulk_add",
            "/admin/prohibited_project_names/bulk/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.prohibited_project_names.remove",
            "/admin/prohibited_project_names/remove/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.prohibited_project_names.release",
            "/admin/prohibited_project_names/release/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.observations.list",
            "/admin/observations/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.list",
            "/admin/malware_reports/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.project.list",
            "/admin/projects/{project_name}/malware_reports/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.project.verdict_not_malware",
            "/admin/projects/{project_name}/malware_reports/not_malware/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.project.verdict_remove_malware",
            "/admin/projects/{project_name}/malware_reports/remove_malware/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.detail",
            "/admin/malware_reports/{observation_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.detail.verdict_not_malware",
            "/admin/malware_reports/{observation_id}/not_malware/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.malware_reports.detail.verdict_remove_malware",
            "/admin/malware_reports/{observation_id}/remove_malware/",
            domain=warehouse,
        ),
        pretend.call("admin.emails.list", "/admin/emails/", domain=warehouse),
        pretend.call("admin.emails.mass", "/admin/emails/mass/", domain=warehouse),
        pretend.call(
            "admin.emails.detail", "/admin/emails/{email_id}/", domain=warehouse
        ),
        pretend.call("admin.flags", "/admin/flags/", domain=warehouse),
        pretend.call("admin.flags.edit", "/admin/flags/edit/", domain=warehouse),
        pretend.call(
            "admin.sponsor.list",
            "/admin/sponsors/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.sponsor.create",
            "/admin/sponsors/create/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.sponsor.delete",
            "/admin/sponsors/{sponsor_id}/delete/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.sponsor.edit",
            "/admin/sponsors/{sponsor_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.banner.list",
            "/admin/banners/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.banner.create",
            "/admin/banners/create/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.banner.delete",
            "/admin/banners/{banner_id}/delete/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.banner.preview",
            "/admin/banners/{banner_id}/preview/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.banner.edit",
            "/admin/banners/{banner_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.helpscout",
            "/admin/helpscout/app/",
            domain=warehouse,
        ),
    ]
