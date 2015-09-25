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

import click

from elasticsearch.helpers import bulk
from sqlalchemy.orm import lazyload, joinedload

from warehouse.cli.search import search
from warehouse.db import Session
from warehouse.packaging.models import Release, Project
from warehouse.packaging.search import Project as ProjectDocType
from warehouse.search import INDEX_NAME, get_index


def _project_docs(db):
    releases = (
        db.query(Release)
          .execution_options(stream_results=True)
          .options(lazyload("*"),
                   joinedload(Release.project)
                   .subqueryload(Project.releases)
                   .load_only("version"))
          .distinct(Release.name)
          .order_by(Release.name, Release._pypi_ordering.desc())
    )
    for release in releases:
        p = ProjectDocType.from_db(release)
        p.full_clean()
        yield p.to_dict(include_meta=True)


@search.command()
@click.pass_obj
def reindex(config, **kwargs):
    """
    Recreate the Search Index.
    """
    client = config.registry["elasticsearch.client"]
    db = Session(bind=config.registry["sqlalchemy.engine"])

    # We use a randomly named index so that we can do a zero downtime reindex.
    # Essentially we'll use a randomly named index which we will use until all
    # of the data has been reindexed, at which point we'll point an alias at
    # our randomly named index, and then delete the old randomly named index.

    # Create the new index and associate all of our doc types with it.
    random_token = binascii.hexlify(os.urandom(5)).decode("ascii")
    new_index_name = "{}-{}".format(INDEX_NAME, random_token)
    doc_types = config.registry.get("search.doc_types", set())
    new_index = get_index(new_index_name, doc_types, using=client)
    new_index.create()

    # From this point on, if any error occurs, we want to be able to delete our
    # in progress index.
    try:
        db.execute(
            """ BEGIN TRANSACTION
                ISOLATION LEVEL SERIALIZABLE
                READ ONLY
                DEFERRABLE
            """
        )
        db.execute("SET statement_timeout = '600s'")

        bulk(client, _project_docs(db))
    except:
        new_index.delete()
        raise
    finally:
        db.rollback()
        db.close()

    # Now that we've finished indexing all of our data, we'll point the alias
    # at our new randomly named index and delete the old index.
    if client.indices.exists_alias(name=INDEX_NAME):
        to_delete = set()
        actions = []
        for name in client.indices.get_alias(name=INDEX_NAME):
            to_delete.add(name)
            actions.append({"remove": {"index": name, "alias": INDEX_NAME}})
        actions.append({"add": {"index": new_index_name, "alias": INDEX_NAME}})
        client.indices.update_aliases({"actions": actions})
        client.indices.delete(",".join(to_delete))
    else:
        client.indices.put_alias(name=INDEX_NAME, index=new_index_name)
