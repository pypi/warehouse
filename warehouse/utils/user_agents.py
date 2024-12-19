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

from pyramid.request import Request


def should_show_share_image(user_agent: str | None) -> bool:
    # User agent header not included or empty
    if not user_agent:
        return True

    # Don't show the og:image for Slackbot link-expansion requests
    if user_agent.strip().startswith("Slackbot-LinkExpanding"):
        return False

    return True
