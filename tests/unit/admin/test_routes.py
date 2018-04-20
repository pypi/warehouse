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
        pretend.call("admin.login", "/admin/login/", domain=warehouse),
        pretend.call("admin.logout", "/admin/logout/", domain=warehouse),
        pretend.call("admin.user.list", "/admin/users/", domain=warehouse),
        pretend.call(
            "admin.user.detail",
            "/admin/users/{user_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.user.delete",
            "/admin/users/{user_id}/delete/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.project.list",
            "/admin/projects/",
            domain=warehouse,
        ),
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
            "admin.project.delete",
            "/admin/projects/{project_name}/delete/",
            factory="warehouse.packaging.models:ProjectFactory",
            traverse="/{project_name}",
            domain=warehouse,
        ),
        pretend.call(
            "admin.journals.list",
            "/admin/journals/",
            domain=warehouse,
        ),
        pretend.call(
            'admin.classifiers',
            '/admin/classifiers/',
            domain=warehouse,
        ),
        pretend.call(
            'admin.classifiers.add',
            '/admin/classifiers/add/',
            domain=warehouse,
        ),
        pretend.call(
            'admin.classifiers.deprecate',
            '/admin/classifiers/deprecate/',
            domain=warehouse,
        ),
        pretend.call(
            "admin.blacklist.list",
            "/admin/blacklist/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.blacklist.add",
            "/admin/blacklist/add/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.blacklist.remove",
            "/admin/blacklist/remove/",
            domain=warehouse,
        ),
        pretend.call("admin.emails.list", "/admin/emails/", domain=warehouse),
        pretend.call(
            "admin.emails.detail",
            "/admin/emails/{email_id}/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.flags",
            "/admin/flags/",
            domain=warehouse,
        ),
        pretend.call(
            "admin.flags.edit",
            "/admin/flags/edit/",
            domain=warehouse,
        ),
    ]
