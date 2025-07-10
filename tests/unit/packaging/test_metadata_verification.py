# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.packaging.metadata_verification import (
    _verify_url_pypi,
    verify_email,
    verify_url,
)


@pytest.mark.parametrize(
    ("url", "project_name", "project_normalized_name", "expected"),
    [
        (  # PyPI /project/ case
            "https://pypi.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # PyPI /p/ case
            "https://pypi.org/p/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # pypi.python.org /project/ case
            "https://pypi.python.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # pypi.python.org /p/ case
            "https://pypi.python.org/p/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # python.org/pypi/  case
            "https://python.org/pypi/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # Normalized name differs from URL
            "https://pypi.org/project/my_project",
            "my_project",
            "my-project",
            True,
        ),
        (  # Normalized name same as URL
            "https://pypi.org/project/my-project",
            "my_project",
            "my-project",
            True,
        ),
        (  # Trailing slash
            "https://pypi.org/project/myproject/",
            "myproject",
            "myproject",
            True,
        ),
        (  # Domains are case insensitive
            "https://PyPI.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # Paths are case-sensitive
            "https://pypi.org/Project/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong domain
            "https://example.com/project/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong path
            "https://pypi.org/something/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Path has extra components
            "https://pypi.org/something/myproject/something",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong package name
            "https://pypi.org/project/otherproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Similar package name
            "https://pypi.org/project/myproject",
            "myproject2",
            "myproject2",
            False,
        ),
        (  # Similar package name
            "https://pypi.org/project/myproject2",
            "myproject",
            "myproject",
            False,
        ),
    ],
)
def test_verify_url_pypi(url, project_name, project_normalized_name, expected):
    assert _verify_url_pypi(url, project_name, project_normalized_name) == expected


def test_verify_url():
    # `verify_url` is just a helper function that calls `_verify_url_pypi` and
    # `OIDCPublisher.verify_url`, where the actual verification logic lives.
    publisher_verifies = pretend.stub(verify_url=lambda url: True)
    publisher_fails = pretend.stub(verify_url=lambda url: False)

    assert verify_url(
        url="https://pypi.org/project/myproject/",
        publisher=None,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert verify_url(
        url="https://github.com/org/myproject/issues",
        publisher=publisher_verifies,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert not verify_url(
        url="example.com",
        publisher=publisher_fails,
        project_name="myproject",
        project_normalized_name="myproject",
    )


@pytest.mark.parametrize(
    ("primary", "public", "verified", "expected"),
    [
        (True, True, True, True),
        (False, True, True, True),
        (True, False, True, False),
        (True, True, False, False),
        (False, False, True, False),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, False, False),
    ],
)
def test_verify_email(db_request, primary, public, verified, expected):
    owner = UserFactory.create()
    maintainer = UserFactory.create()

    EmailFactory.create(
        user=owner,
        email="owner@example.com",
        primary=primary,
        public=public,
        verified=verified,
    )
    EmailFactory.create(
        user=maintainer,
        email="maintainer@example.com",
        primary=primary,
        public=public,
        verified=verified,
    )
    project = ProjectFactory.create()
    RoleFactory.create(user=owner, project=project)
    RoleFactory.create(user=maintainer, project=project, role_name="Maintainer")

    # Emails associated with the project, with different primary/public/verified values
    assert verify_email(email="owner@example.com", project=project) == expected
    assert verify_email(email="maintainer@example.com", project=project) == expected
    assert (
        verify_email(email="Owner name <owner@example.com>", project=project)
        == expected
    )
    assert (
        verify_email(email="Maintainer name <maintainer@example.com>", project=project)
        == expected
    )

    # Emails not associated with the project
    assert not verify_email(email="other@example.com", project=project)
    assert not verify_email(email="Other name <other@example.com>", project=project)
