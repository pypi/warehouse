# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.observations.models import ObservationKind, Observer

# Every flag that grants some admin role. Naming one picks the role outright,
# so a test asserting that a moderator is turned away cannot accidentally get a
# superuser as well and pass without exercising anything.
_ADMIN_ROLES = frozenset(
    {"is_superuser", "is_support", "is_moderator", "is_psf_staff", "is_observer"}
)


@pytest.fixture
def login_admin(login_user):
    """Create an admin user and log it in, returning the user.

    Defaults to a superuser; naming any role flag replaces that default, e.g.
    ``login_admin(is_moderator=True)`` logs in a moderator and nothing more.
    """

    def _login(**kwargs):
        roles = {} if _ADMIN_ROLES & kwargs.keys() else {"is_superuser": True}
        return login_user(
            UserFactory.create(
                **{
                    **roles,
                    "with_verified_primary_email": True,
                    "clear_pwd": "password",
                    **kwargs,
                }
            )
        )

    return _login


@pytest.fixture
def make_malware_report(webtest):
    """Record a malware observation on a fresh project, returning the observation.

    Against an empty database every admin tile renders its "N/A" or
    `{% if %}`-skipped variant, so the richest prop combinations need data.
    """

    def _make(actions: dict | None = None):
        db_sess = webtest.extra_environ["warehouse.db_session"]
        reporter = UserFactory.create()
        reporter.observer = Observer()
        project = ProjectFactory.create()
        observation = project.Observation(
            kind=ObservationKind.IsMalware.value[0],
            observer=reporter.observer,
            payload={},
            actions=actions or {},
            related=project,
            related_name=repr(project),
            summary="Malware report",
        )
        db_sess.add(observation)
        db_sess.flush()
        return observation

    return _make
