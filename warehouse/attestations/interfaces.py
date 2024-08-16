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

from pypi_attestations import Attestation, Distribution
from pyramid.request import Request
from zope.interface import Interface


class IReleaseVerificationService(Interface):

    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def persist_attestations(attestations: list[Attestation], file):
        """
        ̦Persist attestations in storage.
        """
        pass

    def parse_attestations(
        request: Request, distribution: Distribution
    ) -> list[Attestation]:
        """
        Process any attestations included in a file upload request
        """

    def generate_and_store_provenance_file(
        oidc_publisher, file, attestations: list[Attestation]
    ) -> None:
        """
        Generate and store a provenance file for a release, its attestations and an OIDCPublisher.
        """

    def get_provenance_digest(file) -> str | None:
        """
        Compute a provenance file digest for a `File` if it exists.
        """
