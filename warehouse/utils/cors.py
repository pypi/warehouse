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

# We want to allow Cross-Origin requests here so that users can interact
# with these endpoints via XHR/Fetch APIs in the browser.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": ", ".join(
        [
            "Content-Type",
            "If-Match",
            "If-Modified-Since",
            "If-None-Match",
            "If-Unmodified-Since",
        ]
    ),
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Max-Age": "86400",  # 1 day.
    "Access-Control-Expose-Headers": ", ".join(["X-PyPI-Last-Serial"]),
}
