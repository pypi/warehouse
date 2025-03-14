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

from zope.interface import implementer

from warehouse.search import interfaces, tasks


@implementer(interfaces.ISearchService)
class SearchService:
    def __init__(self, **kwargs):
        pass

    @classmethod
    def create_service(cls, context, request):
        return cls()

    def reindex(self, config, projects_to_update):
        for project in projects_to_update:
            config.task(tasks.reindex_project).delay(project.normalized_name)

    def unindex(self, config, projects_to_delete):
        for project in projects_to_delete:
            config.task(tasks.unindex_project).delay(project.normalized_name)


@implementer(interfaces.ISearchService)
class NullSearchService:
    def __init__(self, **kwargs):
        pass

    @classmethod
    def create_service(cls, context, request):
        return cls()

    def reindex(self, config, projects_to_update):
        pass

    def unindex(self, config, projects_to_delete):
        pass
