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

from elasticsearch_dsl import DocType, Text, Keyword, analyzer, MetaField, Date
from first import first
from packaging.version import parse as parse_version

from warehouse.search.utils import doc_type


EmailAnalyzer = analyzer(
    "email",
    tokenizer="uax_url_email",
    filter=["standard", "lowercase", "stop", "snowball"],
)

NameAnalyzer = analyzer(
    "normalized_name",
    tokenizer="lowercase",
    filter=["standard", "lowercase", "word_delimiter"],
)


@doc_type
class Project(DocType):

    name = Text()
    normalized_name = Text(analyzer=NameAnalyzer, index_options="docs")
    version = Keyword(multi=True)
    latest_version = Keyword()
    summary = Text(analyzer="snowball")
    description = Text(analyzer="snowball")
    author = Text()
    author_email = Text(analyzer=EmailAnalyzer)
    maintainer = Text()
    maintainer_email = Text(analyzer=EmailAnalyzer)
    license = Text()
    home_page = Keyword()
    download_url = Keyword()
    keywords = Text(analyzer="snowball")
    platform = Keyword()
    created = Date()
    classifiers = Keyword(multi=True)

    class Meta:
        # disable the _all field to save some space
        all = MetaField(enabled=False)

    @classmethod
    def from_db(cls, release):
        obj = cls(meta={"id": release.project.normalized_name})
        obj["name"] = release.project.name
        obj["normalized_name"] = release.project.normalized_name
        obj["version"] = [
            r.version
            for r in sorted(
                release.project.releases,
                key=lambda r: parse_version(r.version),
                reverse=True,
            )
        ]
        obj["latest_version"] = first(
            sorted(
                release.project.releases,
                key=lambda r: parse_version(r.version),
                reverse=True,
            ),
            key=lambda r: not r.is_prerelease,
            default=release.project.releases[0],
        ).version
        obj["summary"] = release.summary
        obj["description"] = release.description
        obj["author"] = release.author
        obj["author_email"] = release.author_email
        obj["maintainer"] = release.maintainer
        obj["maintainer_email"] = release.maintainer_email
        obj["home_page"] = release.home_page
        obj["download_url"] = release.download_url
        obj["keywords"] = release.keywords
        obj["platform"] = release.platform
        obj["created"] = release.created
        obj["classifiers"] = list(release.classifiers)

        return obj
