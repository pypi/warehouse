# SPDX-License-Identifier: Apache-2.0

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
