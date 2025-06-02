# SPDX-License-Identifier: Apache-2.0

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
