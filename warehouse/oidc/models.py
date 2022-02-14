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


from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from warehouse import db


class OIDCProvider(db.Model):
    __tablename__ = "oidc_providers"

    discriminator = Column(String)

    __mapper_args__ = {"polymorphic_on": discriminator}

    def verify_claims(self, signed_token):
        return NotImplemented


class GitHubProvider(OIDCProvider):
    __tablename__ = "github_oidc_providers"
    __mapper_args__ = {"polymorphic_identity": "GitHubProvider"}

    id = Column(UUID(as_uuid=True), ForeignKey(OIDCProvider.id), primary_key=True)
    repository_name = Column(String)
    owner = Column(String)
    owner_id = Column(String)
    workflow_name = Column(String)

    def repository(self):
        return f"{self.owner}/{self.repository_name}"

    def job_workflow_ref(self):
        return f"{self.repository}/.github/workflows/{self.workflow_name}.yml"

    def verify_claims(self, signed_token):
        """
        Given a JWT that has been successfully decoded (checked for a valid
        signature and basic claims), verify it against the more specific
        claims of this provider.
        """
        return NotImplemented
