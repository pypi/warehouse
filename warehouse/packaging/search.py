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

from opensearchpy import Date, Document, Keyword, Text, analyzer

from warehouse.search.utils import doc_type

EmailAnalyzer = analyzer(
    "email",
    tokenizer="uax_url_email",
    filter=["lowercase", "stop", "snowball"],
)

NameAnalyzer = analyzer(
    "normalized_name",
    tokenizer="lowercase",
    filter=["lowercase", "word_delimiter"],
)


@doc_type
class Project(Document):
    name = Text()
    normalized_name = Text(analyzer=NameAnalyzer)
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

    @classmethod
    def from_db(cls, release):
        obj = cls(meta={"id": release.normalized_name})
        obj["name"] = release.name
        obj["normalized_name"] = release.normalized_name
        obj["latest_version"] = release.latest_version
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
        obj["classifiers"] = release.classifiers

        return obj

    class Index:
        # make sure this class can match any index so it will always be used to
        # deserialize data coming from opensearch.
        name = "*"
