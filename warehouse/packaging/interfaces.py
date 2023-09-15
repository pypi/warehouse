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

from zope.interface import Interface

from warehouse.rate_limiting.interfaces import RateLimiterException


class TooManyProjectsCreated(RateLimiterException):
    pass


class IGenericFileStorage(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def get(path):
        """
        Return a file like object that can be read to access the file located
        at the given path.
        """

    def get_metadata(path):
        """
        Return a dictionary containing any user-created metadata associated
        with the file at a given path. Implementations may or may not store
        or provide such metadata.
        """

    def get_checksum(path):
        """
        Return the md5 digest of the file at a given path as a lowercase string.
        """

    def store(path, file_path, *, meta=None):
        """
        Save the file located at file_path to the file storage at the location
        specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.
        """

    def store_fileobj(path, fileobj, *, meta=None):
        """
        Save the contents of the file like object fileobj to the file storage at the
        location specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.

        This method should set the fileobj back to the stream position it was in
        before returning. Something like:

        _initial_pos = fileobj.tell()
        try:
            ... # do whatever you need to do to persist the contents
        finally:
            fileobj.seek(_initial_pos)
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
    def create_project(name, creator, request, *, creator_is_owner=True):
        """
        Creates a new project, recording a user as its creator.

        If `creator_is_owner`, a `Role` is also added to the project
        marking `creator` as a project owner.
        """
