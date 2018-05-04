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
import urllib
import os

from elasticsearch.helpers import parallel_bulk
from elasticsearch_dsl import serializer
from sqlalchemy import and_, func
from sqlalchemy.orm import aliased
import certifi
import elasticsearch

from warehouse.packaging.models import (
    Classifier, Project, Release, release_classifiers)
from warehouse.packaging.search import Project as ProjectDocType
from warehouse.search.utils import get_index
from warehouse import tasks
from warehouse.utils.db import windowed_query


def _project_docs(db):

    releases_list = (
        db.query(Release.name, Release.version)
        .order_by(
            Release.name,
            Release.is_prerelease.nullslast(),
            Release._pypi_ordering.desc(),
        )
        .distinct(Release.name)
        .subquery("release_list")
    )

    r = aliased(Release, name="r")

    all_versions = (
        db.query(func.array_agg(r.version))
        .filter(r.name == Release.name)
        .correlate(Release)
        .as_scalar()
        .label("all_versions")
    )

    classifiers = (
        db.query(func.array_agg(Classifier.classifier))
        .select_from(release_classifiers)
        .join(Classifier, Classifier.id == release_classifiers.c.trove_id)
        .filter(Release.name == release_classifiers.c.name)
        .filter(Release.version == release_classifiers.c.version)
        .correlate(Release)
        .as_scalar()
        .label("classifiers")
    )

    release_data = (
        db.query(
            Release.description,
            Release.name,
            Release.version.label("latest_version"),
            all_versions,
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
        .select_from(releases_list)
        .join(Release, and_(
            Release.name == releases_list.c.name,
            Release.version == releases_list.c.version))
        .outerjoin(Release.project)
        .order_by(Release.name)
    )

    for release in windowed_query(release_data, Release.name, 50000):
        p = ProjectDocType.from_db(release)
        p.full_clean()
        yield p.to_dict(include_meta=True)


@tasks.task(ignore_result=True, acks_late=True)
def reindex(request):
    """
    Recreate the Search Index.
    """
    p = urllib.parse.urlparse(request.registry.settings["elasticsearch.url"])
    client = elasticsearch.Elasticsearch(
        [urllib.parse.urlunparse(p[:2] + ("",) * 4)],
        verify_certs=True,
        ca_certs=certifi.where(),
        timeout=30,
        retry_on_timeout=True,
        serializer=serializer.serializer,
    )
    number_of_replicas = request.registry.get("elasticsearch.replicas", 0)
    refresh_interval = request.registry.get("elasticsearch.interval", "1s")

    # We use a randomly named index so that we can do a zero downtime reindex.
    # Essentially we'll use a randomly named index which we will use until all
    # of the data has been reindexed, at which point we'll point an alias at
    # our randomly named index, and then delete the old randomly named index.

    # Create the new index and associate all of our doc types with it.
    index_base = request.registry["elasticsearch.index"]
    random_token = binascii.hexlify(os.urandom(5)).decode("ascii")
    new_index_name = "{}-{}".format(index_base, random_token)
    doc_types = request.registry.get("search.doc_types", set())
    shards = request.registry.get("elasticsearch.shards", 1)

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
        request.db.execute("SET statement_timeout = '600s'")

        for _ in parallel_bulk(client, _project_docs(request.db)):
            pass
    except:  # noqa
        new_index.delete()
        raise
    finally:
        request.db.rollback()
        request.db.close()

    # Now that we've finished indexing all of our data we can optimize it and
    # update the replicas and refresh intervals.
    client.indices.forcemerge(index=new_index_name)
    client.indices.put_settings(
        index=new_index_name,
        body={
            "index": {
                "number_of_replicas": number_of_replicas,
                "refresh_interval": refresh_interval,
            }
        }
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
