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

from enum import StrEnum


class Permissions(StrEnum):
    """
    Permissions can be specified in an ACL (`__acl__`) or `@view_config(permission=...)`
    instead of using a string literal, minimizing the chance of typos.

    They are also disconnected from Principals (users, groups, etc.), so they can be
    used in a more generic way. For example, a permission could be used to allow a user
    to edit their own profile, or to allow a group to edit any profile.

    Naming should follow the format:
        <optional scope>:<resource>:<action>

    Where:
        scope: The scope of the permission, such as "admin", "manage", "api"
        resource: The resource being accessed
        action: The action being performed on the resource

    Keep the list alphabetized. Add spacing between logical groupings.
    """

    AdminBannerRead = "admin:banner:read"
    AdminBannerWrite = "admin:banner:write"

    AdminSponsorsRead = "admin:sponsors:read"
    AdminSponsorsWrite = "admin:sponsors:write"
