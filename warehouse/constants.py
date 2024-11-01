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

ONE_MIB = 1 * 1024 * 1024
ONE_GIB = 1 * 1024 * 1024 * 1024
MAX_FILESIZE = 100 * ONE_MIB
MAX_PROJECT_SIZE = 10 * ONE_GIB

MIME_TEXT_HTML = "text/html"
MIME_PYPI_SIMPLE_V1_HTML = "application/vnd.pypi.simple.v1+html"
MIME_PYPI_SIMPLE_V1_JSON = "application/vnd.pypi.simple.v1+json"

MIME_PYPI_SIMPLE_V1_ALL = [
    MIME_PYPI_SIMPLE_V1_JSON,
    MIME_PYPI_SIMPLE_V1_HTML,
]
