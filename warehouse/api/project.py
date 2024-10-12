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

from pyramid.view import view_config
from warehouse.packaging.models import (
    Release,
)
# TODO: Refactor these so they don't come from legacy.
from warehouse.legacy.api.json import (
    _RELEASE_CACHE_DECORATOR,
    json_release,
)


@view_config(
    route_name="api.release",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
    accept="application/json",
    request_method="POST",
    require_methods=["POST"],
    uses_session=True,
    require_csrf=False,
)
def json_release_modify(release, request):
    body = request.json_body
    data = json_release(release, request)
    data['JSON'] = body
    return data


@view_config(
    route_name="api.release",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
    request_method="GET",
)
def json_release_get(release, request):
    return json_release(release, request)
