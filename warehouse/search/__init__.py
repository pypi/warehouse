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

import urllib.parse

import certifi
import elasticsearch

from celery.schedules import crontab
from elasticsearch_dsl import serializer

from warehouse import db
from warehouse.search.utils import get_index
from warehouse.packaging.models import Project, Release


@db.listens_for(db.Session, "after_flush")
def store_projects_for_project_reindex(config, session, flush_context):
    # We'll (ab)use the session.info dictionary to store a list of pending
    # Project updates to the session.
    projects_to_update = session.info.setdefault(
        "warehouse.search.project_updates", set())
    projects_to_delete = session.info.setdefault(
        "warehouse.search.project_deletes", set())

    # Go through each new, changed, and deleted object and attempt to store
    # a Project to reindex for when the session has been committed.
    for obj in (session.new | session.dirty):
        if obj.__class__ == Project:
            projects_to_update.add(obj)
        if obj.__class__ == Release:
            projects_to_update.add(obj.project)

    for obj in (session.deleted):
        if obj.__class__ == Project:
            projects_to_delete.add(obj)
        if obj.__class__ == Release:
            projects_to_update.add(obj.project)


@db.listens_for(db.Session, "after_commit")
def execute_project_reindex(config, session):
    projects_to_update = session.info.pop(
        "warehouse.search.project_updates", set())
    projects_to_delete = session.info.pop(
        "warehouse.search.project_deletes", set())

    from warehouse.search.tasks import reindex_project, unindex_project

    for project in projects_to_update:
        config.task(reindex_project).delay(project.normalized_name)

    for project in projects_to_delete:
        config.task(unindex_project).delay(project.normalized_name)


def es(request):
    client = request.registry["elasticsearch.client"]
    doc_types = request.registry.get("search.doc_types", set())
    index_name = request.registry["elasticsearch.index"]
    index = get_index(
        index_name,
        doc_types,
        using=client,
        shards=request.registry.get("elasticsearch.shards", 1),
        replicas=request.registry.get("elasticsearch.replicas", 0),
    )
    return index.search()


def includeme(config):
    p = urllib.parse.urlparse(config.registry.settings["elasticsearch.url"])
    qs = urllib.parse.parse_qs(p.query)
    config.registry["elasticsearch.client"] = elasticsearch.Elasticsearch(
        [urllib.parse.urlunparse(p[:2] + ("",) * 4)],
        verify_certs=True,
        ca_certs=certifi.where(),
        timeout=30,
        retry_on_timeout=True,
        serializer=serializer.serializer,
    )
    config.registry["elasticsearch.index"] = p.path.strip("/")
    config.registry["elasticsearch.shards"] = int(qs.get("shards", ["1"])[0])
    config.registry["elasticsearch.replicas"] = \
        int(qs.get("replicas", ["0"])[0])
    config.add_request_method(es, name="es", reify=True)

    from warehouse.search.tasks import reindex
    config.add_periodic_task(crontab(minute=0, hour='*/3'), reindex)
