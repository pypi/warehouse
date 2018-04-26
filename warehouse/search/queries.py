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

SEARCH_FIELDS = [
    "author", "author_email", "description", "download_url", "home_page",
    "keywords", "license", "maintainer", "maintainer_email", "normalized_name",
    "platform", "summary",
]
SEARCH_BOOSTS = {
    "name": 10,
    "normalized_name": 10,
    "description": 5,
    "keywords": 5,
    "summary": 5,
}
SEARCH_FILTER_ORDER = (
    "Framework",
    "Topic",
    "Development Status",
    "License",
    "Programming Language",
    "Operating System",
    "Environment",
    "Intended Audience",
    "Natural Language",
)
