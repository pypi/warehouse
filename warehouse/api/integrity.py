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

from pyramid.httpexceptions import HTTPForbidden, HTTPNotAcceptable, HTTPNotFound
from pyramid.request import Request
from pyramid.view import view_config

from warehouse.admin.flags import AdminFlagValue
from warehouse.cache.http import add_vary, cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File
from warehouse.utils.cors import _CORS_HEADERS

MIME_APPLICATION_JSON = "application/json"
MIME_PYPI_INTEGRITY_V1_JSON = "application/vnd.pypi.integrity.v1+json"


def _select_content_type(request: Request) -> str | None:
    offers = request.accept.acceptable_offers(
        [
            # JSON currently has the highest priority.
            MIME_PYPI_INTEGRITY_V1_JSON,
            MIME_APPLICATION_JSON,
        ]
    )

    # Client provided an Accept header, but none of the offers matched.
    if not offers:
        return None
    else:
        return offers[0][0]


@view_config(
    route_name="integrity.provenance",
    context=File,
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
    decorator=[
        add_vary("Accept"),
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def provenance_for_file(file: File, request: Request):
    # Determine our response content-type. For the time being, only the JSON
    # type is accepted.
    request.response.content_type = _select_content_type(request)
    if not request.response.content_type:
        return HTTPNotAcceptable(json={"message": "Request not acceptable"})

    if request.flags.enabled(AdminFlagValue.DISABLE_PEP740):
        return HTTPForbidden(json={"message": "Attestations temporarily disabled"})

    if not file.provenance:
        return HTTPNotFound(
            json={"message": f"No provenance available for {file.filename}"}
        )

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    return file.provenance.provenance
