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


class ISponsorLogoStorage(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def store(path, file_path, content_type=None, *, meta=None):
        """
        Save the file located at file_path to the file storage at the location
        specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.

        Returns public URL for the stored file.
        """
