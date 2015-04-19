"""
Indexes sqlalchemy changes to elasticsearch. It does not handle
db cascades so they should be avoided.
"""

import transaction
from sqlalchemy import event
from elasticsearch import Elasticsearch
from pyramid.threadlocal import get_current_registry

from warehouse.db import _Session
from warehouse.packaging.models import Release


release_defaults = dict(index="warehouse",
                        doc_type="release")

def handle_insert(elasticsearch_url, target):
    es = Elasticsearch([es_url])
    es.index(id=target.name,
             body={"name": target.name,
                   "version": target.version,
                   "description": target.description,
                   "summary": target.summary,
                   "license": target.license,
                   "download_url": target.download_url},
             **release_defaults)

def handle_delete(elasticsearch_url, target):
    es = Elasticsearch([es_url])
    es.delete(id=target.id, **release_defaults)

def includeme(config):
    """Register elasticsearch callbacks"""
    elasticsearch_url = config.registry.settings["elasticsearch.url"]

    @event.listens_for(Release, 'after_insert')
    @event.listens_for(Release, 'after_update')
    def release_insert_update(mapper, connection, target):
        """Signal insert/update events for Release model"""
        tx = transaction.get()
        tx.addAfterCommitHook(handle_insert, args=(elasticsearch_url, target))

    @event.listens_for(Release, 'before_delete')
    def release_delete(mapper, connection, target):
        """Signal idelete event for Release model"""
        tx = transaction.get()
        tx.addAfterCommitHook(handle_delete, args=(elasticsearch_url, target))

    @event.listens_for(_Session, 'after_bulk_update')
    def release_after_bulk_update(update_context):
        import pdb;pdb.set_trace()

    @event.listens_for(_Session, 'before_bulk_delete')
    def release_after_bulk_delete(update_context):
        """Get affected ids before they are deleted"""
        import pdb;pdb.set_trace()