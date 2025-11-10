# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from uuid import UUID

from zope.interface import Interface

from warehouse.rate_limiting.interfaces import RateLimiterException

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import Project


class TooManyProjectsCreated(RateLimiterException):
    pass


class IGenericFileStorage(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def get(path: str):
        """
        Return a file like object that can be read to access the file located
        at the given path.
        """

    def get_metadata(path: str):
        """
        Return a dictionary containing any user-created metadata associated
        with the file at a given path. Implementations may or may not store
        or provide such metadata.
        """

    def get_checksum(path: str):
        """
        Return the md5 digest of the file at a given path as a lowercase string.
        """

    def store(path: str, file_path, *, meta=None):
        """
        Save the file located at file_path to the file storage at the location
        specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.
        """


class IFileStorage(IGenericFileStorage):
    pass


class ISimpleStorage(IGenericFileStorage):
    pass


class IDocsStorage(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def remove_by_prefix(prefix):
        """
        Remove all files matching the given prefix.
        """


class IProjectService(Interface):
    def check_project_name(name):
        """
        Check if a project name is valid and available for use.
        """

    def create_project(
        name,
        creator,
        request,
        *,
        creator_is_owner=True,
        organization_id: UUID | None = None,
    ):
        """
        Creates a new project, recording a user as its creator.

        If `creator_is_owner`, a `Role` is also added to the project
        marking `creator` as a project owner.
        """


class ProjectNameUnavailableError(Exception):
    """Base exception for project name unavailability errors."""

    pass


class ProjectNameUnavailableInvalidError(ProjectNameUnavailableError):
    """Project name is invalid."""

    pass


class ProjectNameUnavailableStdlibError(ProjectNameUnavailableError):
    """Project name conflicts with Python stdlib module."""

    pass


class ProjectNameUnavailableExistingError(ProjectNameUnavailableError):
    """Project name conflicts with existing project."""

    def __init__(self, existing_project: Project):
        self.existing_project: Project = existing_project


class ProjectNameUnavailableProhibitedError(ProjectNameUnavailableError):
    """Project name is prohibited."""

    pass


class ProjectNameUnavailableSimilarError(ProjectNameUnavailableError):
    """Project name is too similar to existing project."""

    def __init__(self, similar_project_name: str):
        self.similar_project_name: str = similar_project_name


class ProjectNameUnavailableTypoSquattingError(ProjectNameUnavailableError):
    """Project name is a typo of an existing project."""

    def __init__(self, check_name: str, existing_project_name: str):
        self.check_name: str = check_name
        self.existing_project_name: str = existing_project_name
