from sqlalchemy import event
from elasticsearch import Elasticsearch
from pyramid.threadlocal import get_current_registry

from warehouse.db import _Session
from warehouse.packaging.models import Release


release_options = dict(index="warehouse",
                       doc_type="release")


def get_elasticsearch():
    """Configures Elasticsearch and returns the object"""
    es_url = get_current_registry().settings["elasticsearch.url"]
    return Elasticsearch([es_url])


@event.listens_for(Release, 'after_insert')
@event.listens_for(Release, 'after_update')
def release_insert_update(mapper, connection, target):
    """Signal insert/update events for Release model"""
    es = get_elasticsearch()
    es.index(id=target.name,
             body={"name": target.name,
                   "version": target.version,
                   "description": target.description,
                   "summary": target.summary,
                   "license": target.license,
                   "download_url": target.download_url},
             **release_options)


@event.listens_for(Release, 'before_delete')
def release_delete(mapper, connection, target):
    """Signal idelete event for Release model"""
    es = get_elasticsearch()
    es.delete(id=target.id, **release_options)


@event.listens_for(_Session, 'after_bulk_update')
def release_after_bulk_update(update_context):
    pass  # TODO: implement


@event.listens_for(_Session, 'after_bulk_delete')
def release_after_bulk_delete(update_context):
    pass  # TODO: implement