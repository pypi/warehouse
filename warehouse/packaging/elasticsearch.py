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
"""
Index sqlalchemy Session changes to ElasticSearch.

It does not handle non-ORM cascades so they should be avoided.
"""

from elasticsearch_dsl import DocType, String, Date, Integer

from warehouse.packaging.models import Release

# TODO: most basic documentation
# TODO: add travis test for server-side cascades?


class ReleaseDoc(DocType):
    name = String(analyzer='snowball')
    version = Integer()
    body = String(analyzer='snowball')
    published_from = Date()
    # TODO: all about those fields

    class Meta:
        index = 'release'
        model = Release

    @classmethod
    def from_model_instance(cls, obj):
        return cls(
            id=obj.name,
            name=obj.name,
            version=obj.version,
            description=obj.description,
            summary=obj.summary,
            license=obj.license,
            download_url=obj.download_url,
        )


def includeme(config):
    config.add_elasticsearch_doctype(ReleaseDoc)