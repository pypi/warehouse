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

from elasticsearch_dsl import DocType, String, analyzer, MetaField

from warehouse.search import doc_type


EmailAnalyzer = analyzer(
    "email",
    tokenizer="uax_url_email",
    filter=["standard", "lowercase", "stop", "snowball"],
)


@doc_type
class Project(DocType):

    name = String()
    normalized_name = String(index="not_analyzed")
    version = String(index="not_analyzed", multi=True)
    summary = String(analyzer="snowball")
    description = String(analyzer="snowball")
    author = String()
    author_email = String(analyzer=EmailAnalyzer)
    maintainer = String()
    maintainer_email = String(analyzer=EmailAnalyzer)
    license = String()
    home_page = String(index="not_analyzed")
    download_url = String(index="not_analyzed")
    keywords = String(analyzer="snowball")
    platform = String(index="not_analyzed")

    uploader_name = String()
    uploader_username = String()

    class Meta:
        # disable the _all field to save some space
        all = MetaField(enabled=False)

    @classmethod
    def from_db(cls, release):
        obj = cls(meta={"id": release.project.normalized_name})
        obj["name"] = release.project.name
        obj["normalized_name"] = release.project.normalized_name
        obj["version"] = [r.version for r in release.project.releases]
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

        obj["uploader_name"] = release.uploader.name
        obj["uploader_username"] = release.uploader.username

        return obj
