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

from sqlalchemy import Boolean, Column, Text, sql

from warehouse import db


class AdminFlagValue(enum.Enum):
    DISABLE_ORGANIZATIONS = "disable-organizations"
    DISALLOW_DELETION = "disallow-deletion"
    DISALLOW_NEW_PROJECT_REGISTRATION = "disallow-new-project-registration"
    DISALLOW_NEW_UPLOAD = "disallow-new-upload"
    DISALLOW_NEW_USER_REGISTRATION = "disallow-new-user-registration"
    DISALLOW_OIDC = "disallow-oidc"
    READ_ONLY = "read-only"


class AdminFlag(db.ModelBase):

    __tablename__ = "admin_flags"

    id = Column(Text, primary_key=True, nullable=False)
    description = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False)
    notify = Column(Boolean, nullable=False, server_default=sql.false())


class Flags:
    def __init__(self, request):
        self.request = request

    def notifications(self):
        return (
            self.request.db.query(AdminFlag)
            .filter(AdminFlag.enabled.is_(True), AdminFlag.notify.is_(True))
            .all()
        )

    def enabled(self, flag_member):
        flag = self.request.db.query(AdminFlag).get(flag_member.value)
        return flag.enabled if flag else False


def includeme(config):
    config.add_request_method(Flags, name="flags", reify=True)
