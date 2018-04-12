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

import hashlib
import urllib.parse

import pyramid.threadlocal

from warehouse.filters import _camo_url


def _hash(email):
    if email is None:
        email = ""

    return hashlib.md5(email.strip().lower().encode("utf8")).hexdigest()


def gravatar(email, size=80):
    request = pyramid.threadlocal.get_current_request()

    camo_url = request.registry.settings["camo.url"].format(request=request)
    camo_key = request.registry.settings["camo.key"]

    url = "https://secure.gravatar.com/avatar/{}".format(_hash(email))
    params = {
        "size": size,
    }

    return _camo_url(
        camo_url,
        camo_key,
        "?".join([url, urllib.parse.urlencode(params)])
    )


def profile(email):
    return "https://gravatar.com/{}".format(_hash(email))
