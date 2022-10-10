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

import enum


class EventTagEnum(str, enum.Enum):
    """Base class for Enum representing Event tags.

    Tags can be broken into three colon-separated parts:
    1. source type
    2. subject type
    3. action

    For example, for event tag "project:role:add":
    1. "project" is the source type
    2. "role" is the subject type
    3. "add" is the action

    In some cases, the subject type can contain a colon:

    For example, for event tag "project:release:file:remove":
    1. "project" is the source type
    2. "release:file" is the subject type
    3. "remove" is the action

    If omitted, subject type is implied to be the same as source type.

    For example, for event tag "project:create":
    1. "project" is the source type
    2. "project" is also the subject type
    3. "create" is the action

    """

    source_type: str
    subject_type: str
    action: str

    # Name = "source_type:subject_type:action"
    def __new__(cls, value: str):
        values = value.split(":")
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.source_type = values[0]
        obj.subject_type = ":".join(values[1:-1]) or value[0]
        obj.action = values[-1]
        return obj


class EventTag:

    class Project(EventTagEnum):
        # Name = "source_type:subject_type:action"
        APITokenAdded = "project:api_token:added"
        APITokenRemoved = "project:api_token:removed"
        OIDCProviderAdded = "project:oidc:provider-added"
        OIDCProviderRemoved = "project:oidc:provider-removed"
        OrganizationProjectAdd = "project:organization_project:add"
        OrganizationProjectRemove = "project:organization_project:remove"
        OwnersRequire2FADisabled = "project:owners_require_2fa:disabled"
        OwnersRequire2FAEnabled = "project:owners_require_2fa:enabled"
        ProjectCreate = "project:create"
        ReleaseAdd = "project:release:add"
        ReleaseFileRemove = "project:release:file:remove"
        ReleaseRemove = "project:release:remove"
        ReleaseUnyank = "project:release:unyank"
        ReleaseYank = "project:release:yank"
        RoleChange = "project:role:change"
        RoleCreate = "project:role:create"
        RoleDelete = "project:role:delete"
        RoleInvite = "project:role:invite"
        RoleRevokeInvite = "project:role:revoke_invite"
        TeamProjectRoleChange = "project:team_project_role:change"
        TeamProjectRoleCreate = "project:team_project_role:create"
        TeamProjectRoleDelete = "project:team_project_role:delete"
        # The following tags are no longer used when recording events.
        # RoleAccepted = "project:role:accepted"
        # RoleAdd = "project:role:add"
