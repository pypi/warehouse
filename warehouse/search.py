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

import elasticsearch
import venusian

from elasticsearch_dsl import Index, Search


INDEX_NAME = "warehouse"


def doc_type(cls):
    def callback(scanner, _name, item):
        types_ = scanner.config.registry.setdefault("search.doc_types", set())
        types_.add(item)

    venusian.attach(cls, callback)

    return cls


def es(request):
    client = request.registry["elasticsearch.client"]
    index = Index(INDEX_NAME, using=client)
    for doc_type in request.registry.get("search.doc_types", set()):
        index.doc_type(doc_type)
    return Search(client)


def includeme(config):
    config.registry["elasticsearch.client"] = elasticsearch.Elasticsearch(
        [config.registry.settings["elasticsearch.url"]],
        verify_certs=True,
    )
    config.add_request_method(es, name="es", reify=True)
