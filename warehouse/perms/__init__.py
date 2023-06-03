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

from warehouse.perms._core import Permission as P, serialize, requires_2fa

# All permissions are required to be defined in this file prior to use to ensure
# that we have a single location that references all of our permissions.
#
# Permissions SHOULD take the form of $resource:$action, unless a different
# format is needed for legacy reasons, which should ideally be aliases.
#
# The permission should generally only be used in an ACL on a type that matches the
# resource or one its children. In other words, Project can have project:*, release:*,
# and file:*, but should not have user:* or org:*.
#
# We should also avoid making "catch all" permissions that operate on too many
# different resources, unless it's an alias for more fine grained permissions.
#
# Permissions can be set to require 2FA, and if they require 2FA then a user will not
# be permitted to use that permission if they do not have 2FA on their account. This
# includes any API tokens that this user has generated.
#
# This enforcement is *only* on the specific named permission, and not any aliased
# permissions. Our views should be using the specific permissions to test against
# anyways, the aliases are primarily for use in ACLs or Macaroon Caveats.

# TODO: Audit for places we're not using the permission system, but we should be

UserManage = P("user:manage")

# TODO: Are these scoped to user only projects, or does it affect organizations as well?
ProjectCreate = P("project:create")
ProjectManage = P("project:manage")  # manage:project

ReleaseCreate = P("release:create")

FileUpload = P("file:upload")


OrgCreate = P("org:create")
OrgView = P("org:view")  # view:organization
OrgManage = P("org:manage")  # # manage:organization
# TODO: Double check manage:billing is only orgs
OrgBilling = P("org:billing")  # manage:billing
# TODO: Double check that add:project is only orgs
OrgAddProject = P("org:add-project")  # add:project


# TODO: Should these be nested? org:team:view? Does that make sense? Maybe org.team:view?
TeamView = P("team:view")  # view:team
TeamManage = P("team:manage")  # manage:team


# TODO: Break these permissions up, these likely don't make sense as they're more
#       like role names than permissions, where roles should be groups that we grant
#       permissions to.
Admin = P("admin")
Moderator = P("Moderator")
PSFStaff = P("psf_staff")
AdminDashboard = P("admin_dashboard_access")


# Aliases

Upload = P("upload", [ProjectCreate, ReleaseCreate, FileUpload])


# Exports

__all__ = ["requires_2fa", "serialize"]
