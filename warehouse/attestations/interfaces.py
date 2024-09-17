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

from __future__ import annotations

from typing import TYPE_CHECKING

from zope.interface import Interface

if TYPE_CHECKING:
    from pypi_attestations import Attestation, Distribution
    from pyramid.request import Request

    from warehouse.attestations.models import Provenance


class IIntegrityService(Interface):
    def create_service(context, request):
        """
        Create the service for the given context and request.
        """

    def parse_attestations(
        request: Request, distribution: Distribution
    ) -> list[Attestation]:
        """
        Process any attestations included in a file upload request.
        """

    def build_provenance(request, file, attestations: list[Attestation]) -> Provenance:
        """
        Construct and persist a provenance object composed of the given attestations,
        and attach it to the given file.
        """
