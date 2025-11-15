# SPDX-License-Identifier: Apache-2.0

import enum

from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.db.types import bool_false


class AdminFlagValue(enum.Enum):
    DISABLE_ORGANIZATIONS = "disable-organizations"
    DISABLE_PEP740 = "disable-pep740"
    DISALLOW_DELETION = "disallow-deletion"
    DISALLOW_NEW_PROJECT_REGISTRATION = "disallow-new-project-registration"
    DISALLOW_NEW_UPLOAD = "disallow-new-upload"
    DISALLOW_NEW_USER_REGISTRATION = "disallow-new-user-registration"
    DISALLOW_OIDC = "disallow-oidc"
    DISALLOW_GITHUB_OIDC = "disallow-github-oidc"
    DISALLOW_GITLAB_OIDC = "disallow-gitlab-oidc"
    DISALLOW_GOOGLE_OIDC = "disallow-google-oidc"
    DISALLOW_ACTIVESTATE_OIDC = "disallow-activestate-oidc"
    DISALLOW_SEMAPHORE_OIDC = "disallow-semaphore-oidc"
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
        self.admin_flags_values = None

    def _fetch_flags(self):
        if self.admin_flags_values is None:
            self.admin_flags_values = {
                f.id: f for f in self.request.db.query(AdminFlag).all()
            }
        return self.admin_flags_values

    def notifications(self):
        return [
            flag
            for flag in self._fetch_flags().values()
            if flag.enabled and flag.notify
        ]

    def disallow_oidc(self, flag_member=None):
        return self.enabled(flag_member) or self.enabled(AdminFlagValue.DISALLOW_OIDC)

    def enabled(self, flag_member):
        flag = self._fetch_flags().get(flag_member.value, None) if flag_member else None
        return flag.enabled if flag else False


def includeme(config):
    config.add_request_method(Flags, name="flags", reify=True)
