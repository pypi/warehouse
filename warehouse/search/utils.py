# SPDX-License-Identifier: Apache-2.0

import venusian

from opensearchpy import Index


def doc_type(cls):
    def callback(scanner, _name, item):
        types_ = scanner.config.registry.setdefault("search.doc_types", set())
        types_.add(item)

    venusian.attach(cls, callback, category="warehouse")

    return cls


def get_index(name, doc_types, *, using, shards=1, replicas=0, interval="1s"):
    index = Index(name, using=using)
    for doc_type in doc_types:
        index.document(doc_type)
    index.settings(
        number_of_shards=shards, number_of_replicas=replicas, refresh_interval=interval
    )
    return index
