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

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound
from pyramid.request import Request
from pyramid.view import view_config

from warehouse.admin.flags import AdminFlagValue
from warehouse.packaging.models import File


@view_config(
    route_name="attestations.provenance",
    context=File,
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def provenance_for_file(file: File, request: Request):
    if request.flags.enabled(AdminFlagValue.DISABLE_PEP740):
        return HTTPForbidden(json={"message": "Attestations temporarily disabled"})

    if not file.provenance:
        return HTTPNotFound(
            json={"message": f"No provenance available for {file.filename}"}
        )

    return file.provenance.provenance
