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

import urllib.parse

import elasticsearch
import venusian

from elasticsearch_dsl import Index


def doc_type(cls):
    def callback(scanner, _name, item):
        types_ = scanner.config.registry.setdefault("search.doc_types", set())
        types_.add(item)

    venusian.attach(cls, callback)

    return cls


def get_index(name, doc_types, *, using):
    index = Index(name, using=using)
    for doc_type in doc_types:
        index.doc_type(doc_type)
    return index


def es(request):
    client = request.registry["elasticsearch.client"]
    doc_types = request.registry.get("search.doc_types", set())
    index_name = request.registry["elasticsearch.index"]
    index = get_index(index_name, doc_types, using=client)
    return index.search()


def includeme(config):
    p = urllib.parse.urlparse(config.registry.settings["elasticsearch.url"])
    config.registry["elasticsearch.client"] = elasticsearch.Elasticsearch(
        [urllib.parse.urlunparse(p[:2] + ("",) * 4)],
        verify_certs=True,
    )
    config.registry["elasticsearch.index"] = p.path.strip("/")
    config.add_request_method(es, name="es", reify=True)
