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

import binascii
import os
import urllib.parse

import certifi
import opensearchpy
import redis
import requests_aws4auth
import sentry_sdk

from opensearchpy.helpers import parallel_bulk
from redis.lock import Lock
from sqlalchemy import func, select, text
from sqlalchemy.orm import aliased
from urllib3.util import parse_url

from warehouse import tasks
from warehouse.packaging.models import (
    Classifier,
    Description,
    Project,
    Release,
    ReleaseClassifiers,
)
from warehouse.packaging.search import Project as ProjectDocument
from warehouse.search.utils import get_index
from warehouse.utils.db import windowed_query


def _project_docs(db, project_name=None):
    releases_list = (
        select(Release.id)
        .filter(Release.yanked.is_(False), Release.files)
        .order_by(
            Release.project_id,
            Release.is_prerelease.nullslast(),
            Release._pypi_ordering.desc(),
        )
        .distinct(Release.project_id)
    )

    if project_name:
        releases_list = releases_list.join(Project).filter(Project.name == project_name)

    releases_list = releases_list.subquery()
    rlist = aliased(Release, releases_list)

    classifiers = (
        select(func.array_agg(Classifier.classifier))
        .select_from(ReleaseClassifiers)
        .join(Classifier, Classifier.id == ReleaseClassifiers.trove_id)
        .filter(Release.id == ReleaseClassifiers.release_id)
        .correlate(Release)
        .scalar_subquery()
        .label("classifiers")
    )

    release_data = (
        select(
            Description.raw.label("description"),
            Release.version.label("latest_version"),
            Release.author,
            Release.author_email,
            Release.maintainer,
            Release.maintainer_email,
            Release.home_page,
            Release.summary,
            Release.keywords,
            Release.platform,
            Release.download_url,
            Release.created,
            classifiers,
            Project.normalized_name,
            Project.name,
        )
        .select_from(rlist)
        .join(Release, Release.id == rlist.id)
        .join(Description)
        .outerjoin(Release.project)
    )

    for chunk in windowed_query(db, release_data, Project.name, 25000):
        for release in chunk:
            p = ProjectDocument.from_db(release)
            p._index = None
            p.full_clean()
            doc = p.to_dict(include_meta=True)
            doc.pop("_index", None)
            yield doc


class SearchLock(Lock):
    def __init__(self, redis_client, timeout=None, blocking_timeout=None):
        super().__init__(
            redis_client,
            name="search-index",
            timeout=timeout,
            blocking_timeout=blocking_timeout,
        )


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def reindex(self, request):
    """
    Recreate the Search Index.
    """
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])
    try:
        with SearchLock(r, timeout=30 * 60, blocking_timeout=30):
            p = parse_url(request.registry.settings["opensearch.url"])
            qs = urllib.parse.parse_qs(p.query)
            kwargs = {
                "hosts": [urllib.parse.urlunparse((p.scheme, p.netloc) + ("",) * 4)],
                "verify_certs": True,
                "ca_certs": certifi.where(),
                "timeout": 30,
                "retry_on_timeout": True,
                "serializer": opensearchpy.serializer.serializer,
            }
            aws_auth = bool(qs.get("aws_auth", False))
            if aws_auth:
                aws_region = qs.get("region", ["us-east-1"])[0]
                kwargs["connection_class"] = opensearchpy.RequestsHttpConnection
                kwargs["http_auth"] = requests_aws4auth.AWS4Auth(
                    request.registry.settings["aws.key_id"],
                    request.registry.settings["aws.secret_key"],
                    aws_region,
                    "es",
                )
            client = opensearchpy.OpenSearch(**kwargs)
            number_of_replicas = request.registry.get("opensearch.replicas", 0)
            refresh_interval = request.registry.get("opensearch.interval", "1s")

            # We use a randomly named index so that we can do a zero downtime reindex.
            # Essentially we'll use a randomly named index which we will use until all
            # of the data has been reindexed, at which point we'll point an alias at
            # our randomly named index, and then delete the old randomly named index.

            # Create the new index and associate all of our doc types with it.
            index_base = request.registry["opensearch.index"]
            random_token = binascii.hexlify(os.urandom(5)).decode("ascii")
            new_index_name = f"{index_base}-{random_token}"
            doc_types = request.registry.get("search.doc_types", set())
            shards = request.registry.get("opensearch.shards", 1)

            # Create the new index with zero replicas and index refreshes disabled
            # while we are bulk indexing.
            new_index = get_index(
                new_index_name,
                doc_types,
                using=client,
                shards=shards,
                replicas=0,
                interval="-1",
            )
            new_index.create(wait_for_active_shards=shards)

            # From this point on, if any error occurs, we want to be able to delete our
            # in progress index.
            try:
                request.db.execute(text("SET statement_timeout = '600s'"))

                for _ in parallel_bulk(
                    client, _project_docs(request.db), index=new_index_name
                ):
                    pass
            except:  # noqa
                new_index.delete()
                raise
            finally:
                request.db.rollback()
                request.db.close()

            # Now that we've finished indexing all of our data we can update the
            # replicas and refresh intervals.
            client.indices.put_settings(
                index=new_index_name,
                body={
                    "index": {
                        "number_of_replicas": number_of_replicas,
                        "refresh_interval": refresh_interval,
                    }
                },
            )

            # Point the alias at our new randomly named index and delete the old index.
            if client.indices.exists_alias(name=index_base):
                to_delete = set()
                actions = []
                for name in client.indices.get_alias(name=index_base):
                    to_delete.add(name)
                    actions.append({"remove": {"index": name, "alias": index_base}})
                actions.append({"add": {"index": new_index_name, "alias": index_base}})
                client.indices.update_aliases({"actions": actions})
                client.indices.delete(",".join(to_delete))
            else:
                client.indices.put_alias(name=index_base, index=new_index_name)
    except redis.exceptions.LockError as exc:
        sentry_sdk.capture_exception(exc)
        raise self.retry(countdown=60, exc=exc)


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def reindex_project(self, request, project_name):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])
    try:
        with SearchLock(r, timeout=15, blocking_timeout=1):
            client = request.registry["opensearch.client"]
            doc_types = request.registry.get("search.doc_types", set())
            index_name = request.registry["opensearch.index"]
            get_index(
                index_name,
                doc_types,
                using=client,
                shards=request.registry.get("opensearch.shards", 1),
                replicas=request.registry.get("opensearch.replicas", 0),
            )

            for _ in parallel_bulk(
                client, _project_docs(request.db, project_name), index=index_name
            ):
                pass
    except redis.exceptions.LockError as exc:
        sentry_sdk.capture_exception(exc)
        raise self.retry(countdown=60, exc=exc)


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def unindex_project(self, request, project_name):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])
    try:
        with SearchLock(r, timeout=15, blocking_timeout=1):
            client = request.registry["opensearch.client"]
            index_name = request.registry["opensearch.index"]
            try:
                client.delete(index=index_name, id=project_name)
            except opensearchpy.exceptions.NotFoundError:
                pass
    except redis.exceptions.LockError as exc:
        sentry_sdk.capture_exception(exc)
        raise self.retry(countdown=60, exc=exc)
