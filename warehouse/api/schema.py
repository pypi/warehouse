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

import datetime

from marshmallow import Schema, fields


class File(Schema):
    filename = fields.Str()
    packagetype = fields.Str()
    python_version = fields.Str()
    has_sig = fields.Bool(attribute="has_signature")
    comment_text = fields.Str()
    md5_digest = fields.Str()
    digests = fields.Method("get_digests")
    size = fields.Int()
    upload_time = fields.Function(
        lambda obj: obj.upload_time.strftime("%Y-%m-%dT%H:%M:%S")
    )
    url = fields.Method("get_detail_url")

    def get_digests(self, obj):
        return {"md5": obj.md5_digest, "sha256": obj.sha256_digest}

    def get_detail_url(self, obj):
        request = self.context.get("request")
        return request.route_url("packaging.file", path=obj.path)


class Release(Schema):
    bugtrack_url = fields.Str(attribute="project.bugtrack_url")
    classifiers = fields.List(fields.Str())
    docs_url = fields.Str(attribute="project.documentation_url")
    downloads = fields.Method("get_downloads")
    project_url = fields.Method("get_project_url")
    url = fields.Method("get_release_url")
    requires_dist = fields.List(fields.Str())
    files_url = fields.Method("get_files_url")

    def get_files_url(self, obj):
        request = self.context.get("request")
        return request.route_url(
            "api.views.projects.releases.files",
            name=obj.project.name,
            version=obj.version,
        )

    def get_project_url(self, obj):
        request = self.context.get("request")
        return request.route_url("api.views.projects.detail", name=obj.project.name)

    def get_release_url(self, obj):
        request = self.context.get("request")
        return request.route_url(
            "api.views.projects.releases.detail",
            name=obj.project.name,
            version=obj.version,
        )

    def get_downloads(self, obj):
        return {"last_day": -1, "last_week": -1, "last_month": -1}

    class Meta:
        fields = (
            "author",
            "author_email",
            "bugtrack_url",
            "classifiers",
            "description",
            "description_content_type",
            "docs_url",
            "downloads",
            "download_url",
            "home_page",
            "keywords",
            "license",
            "maintainer",
            "maintainer_email",
            "name",
            "project_url",
            "url",
            "platform",
            "requires_dist",
            "requires_python",
            "summary",
            "version",
            "files_url",
        )
        ordered = True


class Project(Schema):
    url = fields.Method("get_detail_url")
    releases_url = fields.Method("get_releases_url")
    latest_version_url = fields.Method("get_latest_version_url")
    legacy_project_json = fields.Method("get_legacy_project_json")
    roles_url = fields.Method("get_roles_url")
    files_url = fields.Method("get_files_url")

    def get_files_url(self, obj):
        request = self.context.get("request")
        return request.route_url("api.views.projects.detail.files", name=obj.name)

    def get_roles_url(self, obj):
        request = self.context.get("request")
        return request.route_url(
            "api.views.projects.detail.roles", name=obj.normalized_name
        )

    def get_legacy_project_json(self, obj):
        request = self.context.get("request")
        return request.route_url("legacy.api.json.project", name=obj.normalized_name)

    def get_detail_url(self, obj):
        request = self.context.get("request")
        return request.route_url("api.views.projects.detail", name=obj.normalized_name)

    def get_latest_version_url(self, obj):
        request = self.context.get("request")
        if not obj.latest_version:
            return None
        return request.route_url(
            "api.views.projects.releases.detail",
            name=obj.name,
            version=obj.latest_version[0],
        )

    def get_releases_url(self, obj):
        request = self.context.get("request")
        return request.route_url(
            "api.views.projects.releases", name=obj.normalized_name
        )

    class Meta:
        fields = (
            "name",
            "normalized_name",
            "latest_version_url",
            "bugtrack_url",
            "last_serial",
            "url",
            "releases_url",
            "legacy_project_json",
            "stable_version",
            "created",
            "roles_url",
            "files_url",
        )


class Journal(Schema):
    project_name = fields.Str(attribute="name")
    timestamp = fields.Method("get_timestamp")
    release_url = fields.Method("get_release_url")

    def get_release_url(self, obj):
        request = self.context.get("request")
        if not obj.version:
            return None
        return request.route_url(
            "api.views.projects.releases.detail", name=obj.name, version=obj.version
        )

    def get_timestamp(self, obj):
        return int(obj.submitted_date.replace(tzinfo=datetime.timezone.utc).timestamp())

    class Meta:
        fields = (
            "project_name",
            "release_url",
            "version",
            "timestamp",
            "action",
            "submitted_date",
        )


class Role(Schema):
    role = fields.Str(attribute="role_name")
    name = fields.Str(attribute="user.username")


class UserProjects(Schema):
    role = fields.Str(attribute="role_name")
    project = fields.Nested(Project(only=("name", "url")))
