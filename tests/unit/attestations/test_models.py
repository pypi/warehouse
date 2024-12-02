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

import pypi_attestations

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import FileFactory


def test_provenance_as_model(db_request, integrity_service, dummy_attestation):
    db_request.oidc_publisher = GitHubPublisherFactory.create()
    file = FileFactory.create()
    provenance = integrity_service.build_provenance(
        db_request, file, [dummy_attestation]
    )

    assert isinstance(provenance.as_model, pypi_attestations.Provenance)
