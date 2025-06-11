# SPDX-License-Identifier: Apache-2.0

import rfc3986

from warehouse.filters import format_email
from warehouse.oidc.models import OIDCPublisher
from warehouse.packaging import Project

_pypi_project_urls = [
    "https://pypi.org/project/",
    "https://pypi.org/p/",
    "https://pypi.python.org/project/",
    "https://pypi.python.org/p/",
    "https://python.org/pypi/",
]


def _verify_url_pypi(url: str, project_name: str, project_normalized_name: str) -> bool:
    """
    Check if a URL matches any of the PyPI URLs for a specific project
    """
    candidate_urls = (
        f"{pypi_project_url}{name}{optional_slash}"
        for pypi_project_url in _pypi_project_urls
        for name in {project_name, project_normalized_name}
        for optional_slash in ["/", ""]
    )

    user_uri = rfc3986.api.uri_reference(url).normalize()
    return any(
        user_uri == rfc3986.api.uri_reference(candidate_url).normalize()
        for candidate_url in candidate_urls
    )


def verify_url(
    url: str,
    publisher: OIDCPublisher | None,
    project_name: str,
    project_normalized_name: str,
) -> bool:
    """
    Verify a URL included in a project's metadata

    This function is intended to be used during file uploads, checking the URLs
    included in the metadata against PyPI URLs for that project and against the Trusted
    Publisher used to authenticate the upload (if any).
    """
    if _verify_url_pypi(
        url=url,
        project_name=project_name,
        project_normalized_name=project_normalized_name,
    ):
        return True

    if not publisher:
        return False

    return publisher.verify_url(url)


def verify_email(email: str, project: Project) -> bool:
    """
    Verify an email address included in a project's metadata

    This function is intended to be used during file uploads, checking the emails
    included in the metadata against the emails of the Owners and Maintainers of that
    PyPI project.
    Note: Only emails that are marked as verified and public are used for verification.
    """
    _, email = format_email(email)
    owner_emails = {
        email.email
        for owner in project.owners
        for email in owner.emails
        if email.public and email.verified
    }
    if email in owner_emails:
        return True
    maintainer_emails = {
        email.email
        for maintainer in project.maintainers
        for email in maintainer.emails
        if email.public and email.verified
    }
    return email in maintainer_emails
