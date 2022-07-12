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
            "admin.organization.approve",
            "/admin/organizations/{organization_id}/approve/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.organization.decline",
            "/admin/organizations/{organization_id}/decline/",
            domain=warehouse,
        ),
        pretend.call("admin.user.list", "/admin/users/", domain=warehouse),
        pretend.call("admin.user.detail", "/admin/users/{user_id}/", domain=warehouse),
        pretend.call(
            "admin.user.add_email",
            "/admin/users/{user_id}/add_email/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.user.delete", "/admin/users/{user_id}/delete/", domain=warehouse
        ),
        pretend.call(
            "admin.user.reset_password",
            "/admin/users/{user_id}/reset_password/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.prohibited_user_names.bulk_add",
            "/admin/prohibited_user_names/bulk/",
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
        pretend.call("admin.emails.list", "/admin/emails/", domain=warehouse),
        pretend.call("admin.emails.mass", "/admin/emails/mass/", domain=warehouse),
        pretend.call(
            "admin.emails.detail", "/admin/emails/{email_id}/", domain=warehouse
        ),
        pretend.call("admin.flags", "/admin/flags/", domain=warehouse),
        pretend.call("admin.flags.edit", "/admin/flags/edit/", domain=warehouse),
        pretend.call("admin.checks.list", "/admin/checks/", domain=warehouse),
        pretend.call(
            "admin.checks.detail", "/admin/checks/{check_name}", domain=warehouse
        ),
        pretend.call(
            "admin.checks.change_state",
            "/admin/checks/{check_name}/change_state",
            domain=warehouse,
        ),
        pretend.call(
            "admin.checks.run_evaluation",
            "/admin/checks/{check_name}/run_evaluation",
            domain=warehouse,
        ),
        pretend.call("admin.verdicts.list", "/admin/verdicts/", domain=warehouse),
        pretend.call(
            "admin.verdicts.detail", "/admin/verdicts/{verdict_id}", domain=warehouse
        ),
        pretend.call(
            "admin.verdicts.review",
            "/admin/verdicts/{verdict_id}/review",
            domain=warehouse,
        ),
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
    ]
