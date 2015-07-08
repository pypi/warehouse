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

import transaction
from sqlalchemy import event
from elasticsearch import Elasticsearch

from warehouse.db import _Session


def add_elasticsearch_doctype(config, doctype):
    doctype.init(using=config.registry.elasticsearch)

    def handle_insert(target):
        obj = doctype.from_model_instance(target)
        obj.save(using=config.registry.elasticsearch)

    def handle_delete(target):
        # TODO: what if id doesn't exist? (add a test)
        obj = doctype.get(id=target.id)
        obj.delete(using=config.registry.elasticsearch)

    @event.listens_for(model, 'after_insert')
    @event.listens_for(model, 'after_update')
    def release_insert_update(mapper, connection, target):
        """Signal insert/update events for the model"""
        tx = transaction.get()
        tx.addAfterCommitHook(handle_insert,
                              args=(target,))

    @event.listens_for(model, 'before_delete')
    def release_delete(mapper, connection, target):
        """Signal idelete event for the model"""
        tx = transaction.get()
        tx.addAfterCommitHook(handle_delete,
                              args=(target,))

    # TODO: our hooks defeat the purpose of bulk queries - these should be ran
    # as part of extrnal process

    # TODO: these two callback currently work for all queries, they should be
    # limited to a specific model

    @event.listens_for(_Session, 'after_bulk_update')
    def release_after_bulk_update(update_context):
        tx = transaction.get()
        for obj in query:
            tx.addAfterCommitHook(handle_delete,
                                  args=(obj,))

    @event.listens_for(_Session, 'before_bulk_delete')
    def release_after_bulk_delete(update_context):
        """Get affected ids before they are deleted"""
        tx = transaction.get()
        for obj in query:
            tx.addAfterCommitHook(handle_delete,
                                  args=(obj,))


def includeme(config):
    es_url = config.registry.settings["elasticsearch.url"]
    config.registry.elasticsearch = Elasticsearch(es_url)
     
    config.add_directive("add_elasticsearch_doctype",
                         add_elasticsearch_doctype, action_wrap=False)