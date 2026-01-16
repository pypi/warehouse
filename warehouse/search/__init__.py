# SPDX-License-Identifier: Apache-2.0

import urllib.parse

import certifi
import opensearchpy
import requests_aws4auth

from celery.schedules import crontab
from urllib3.util import parse_url

from warehouse import db
from warehouse.packaging.models import LifecycleStatus, Project, Release
from warehouse.rate_limiting import IRateLimiter, RateLimit
from warehouse.search.interfaces import ISearchService
from warehouse.search.services import SearchService
from warehouse.search.utils import get_index


@db.listens_for(db.Session, "after_flush")
def store_projects_for_project_reindex(config, session, flush_context):
    # We'll (ab)use the session.info dictionary to store a list of pending
    # Project updates to the session.
    projects_to_update = session.info.setdefault(
        "warehouse.search.project_updates", set()
    )
    projects_to_delete = session.info.setdefault(
        "warehouse.search.project_deletes", set()
    )

    # Go through each new, changed, and deleted object and attempt to store
    # a Project to reindex for when the session has been committed.
    for obj in session.new | session.dirty:
        if obj.__class__ == Project:
            # Un-index archived/quarantined projects
            if obj.lifecycle_status in [
                LifecycleStatus.QuarantineEnter,
                LifecycleStatus.ArchivedNoindex,
            ]:
                projects_to_delete.add(obj)
            else:
                projects_to_update.add(obj)
        if obj.__class__ == Release:
            projects_to_update.add(obj.project)

    for obj in session.deleted:
        if obj.__class__ == Project:
            projects_to_delete.add(obj)
        if obj.__class__ == Release:
            projects_to_update.add(obj.project)


@db.listens_for(db.Session, "after_commit")
def execute_project_reindex(config, session):
    try:
        search_service_factory = config.find_service_factory(ISearchService)
    except LookupError:
        return

    projects_to_update = session.info.pop("warehouse.search.project_updates", set())
    projects_to_delete = session.info.pop("warehouse.search.project_deletes", set())

    search_service = search_service_factory(None, config)
    search_service.reindex(config, projects_to_update)
    search_service.unindex(config, projects_to_delete)


def opensearch(request):
    client = request.registry["opensearch.client"]
    doc_types = request.registry.get("search.doc_types", set())
    index_name = request.registry["opensearch.index"]
    index = get_index(
        index_name,
        doc_types,
        using=client,
        shards=request.registry.get("opensearch.shards", 1),
        replicas=request.registry.get("opensearch.replicas", 0),
    )
    return index.search()


def includeme(config):
    ratelimit_string = config.registry.settings.get("warehouse.search.ratelimit_string")
    config.register_service_factory(
        RateLimit(ratelimit_string), IRateLimiter, name="search"
    )

    p = parse_url(config.registry.settings["opensearch.url"])
    assert p.path, "The URL for the OpenSearch instance must include the index name."
    qs = urllib.parse.parse_qs(p.query)
    kwargs = {
        "hosts": [urllib.parse.urlunparse((p.scheme, p.netloc) + ("",) * 4)],
        "verify_certs": True,
        "ca_certs": certifi.where(),
        "timeout": 1,
        "retry_on_timeout": True,
        "serializer": opensearchpy.serializer.serializer,
        "max_retries": 1,
    }
    aws_auth = bool(qs.get("aws_auth", False))
    if aws_auth:
        aws_region = qs.get("region", ["us-east-1"])[0]
        kwargs["connection_class"] = opensearchpy.RequestsHttpConnection
        kwargs["http_auth"] = requests_aws4auth.AWS4Auth(
            config.registry.settings["aws.key_id"],
            config.registry.settings["aws.secret_key"],
            aws_region,
            "es",
        )
    config.registry["opensearch.client"] = opensearchpy.OpenSearch(**kwargs)
    config.registry["opensearch.index"] = p.path.strip("/")
    config.registry["opensearch.shards"] = int(qs.get("shards", ["1"])[0])
    config.registry["opensearch.replicas"] = int(qs.get("replicas", ["0"])[0])
    config.add_request_method(opensearch, name="opensearch", reify=True)

    from warehouse.search.tasks import reindex

    config.add_periodic_task(crontab(minute=0, hour=6), reindex)

    config.register_service_factory(SearchService.create_service, iface=ISearchService)
