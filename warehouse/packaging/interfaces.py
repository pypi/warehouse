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


class IDownloadStatService(Interface):

    def get_daily_stats(project):
        """
        Return the daily download counts for the given project.
        """

    def get_weekly_stats(project):
        """
        Return the weekly download counts for the given project.
        """

    def get_monthly_stats(project):
        """
        Return the monthly download counts for the given project.
        """


class IFileStorage(Interface):

    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def get(path):
        """
        Return a file like object that can be read to access the file located
        at the given path.
        """

    def store(path, file_path, *, meta=None):
        """
        Save the file located at file_path to the file storage at the location
        specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.
        """
