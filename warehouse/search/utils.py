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
