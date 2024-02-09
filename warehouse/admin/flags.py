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

from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.db.types import bool_false


class AdminFlagValue(enum.Enum):
    DISABLE_ORGANIZATIONS = "disable-organizations"
    DISALLOW_DELETION = "disallow-deletion"
    DISALLOW_NEW_PROJECT_REGISTRATION = "disallow-new-project-registration"
    DISALLOW_NEW_UPLOAD = "disallow-new-upload"
    DISALLOW_NEW_USER_REGISTRATION = "disallow-new-user-registration"
    DISALLOW_OIDC = "disallow-oidc"
    DISALLOW_GITHUB_OIDC = "disallow-github-oidc"
    DISALLOW_GOOGLE_OIDC = "disallow-google-oidc"
    DISALLOW_ACTIVESTATE_OIDC = "disallow-activestate-oidc"
    READ_ONLY = "read-only"


class AdminFlag(db.ModelBase):
    __tablename__ = "admin_flags"

    id: Mapped[str] = mapped_column(primary_key=True)
    description: Mapped[str]
    enabled: Mapped[bool]
    notify: Mapped[bool_false]


class Flags:
    def __init__(self, request):
        self.request = request

    def notifications(self):
        return (
            self.request.db.query(AdminFlag)
            .filter(AdminFlag.enabled.is_(True), AdminFlag.notify.is_(True))
            .all()
        )

    def disallow_oidc(self, flag_member=None):
        return self.enabled(flag_member) or self.enabled(AdminFlagValue.DISALLOW_OIDC)

    def enabled(self, flag_member):
        flag = (
            self.request.db.get(AdminFlag, flag_member.value) if flag_member else None
        )
        return flag.enabled if flag else False


def includeme(config):
    config.add_request_method(Flags, name="flags", reify=True)
