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

import os

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    sql,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from warehouse import db


def _generate_key():
    return os.urandom(32)


class Macaroon(db.Model):

    __tablename__ = "macaroons"
    __table_args__ = (
        UniqueConstraint(
            "description", "user_id", name="_user_macaroons_description_uc"
        ),
        UniqueConstraint(
            "description", "project_id", name="_project_macaroons_description_uc"
        ),
        CheckConstraint(
            "(user_id::text IS NULL) <> (project_id::text IS NULL)",
            name="_user_xor_project_macaroon",
        ),
    )

    # Macaroons come in two forms: they either belong to a user, or they
    # belong to a project.
    # * In the user case, a Macaroon has an associated user, and *might* have
    #   additional project scope restrictions as part of its caveats.
    # * In the project case, a Macaroon has an associated project, and
    #   is scoped to just that project.
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True
    )

    # Store some information about the Macaroon to give users some mechanism
    # to differentiate between them.
    description = Column(String(100), nullable=False)
    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    last_used = Column(DateTime, nullable=True)

    # Human-readable "permissions" for this macaroon, corresponding to the
    # body of the permissions ("V1") caveat.
    permissions_caveat = Column(JSONB, nullable=False, server_default=sql.text("'{}'"))

    # It might be better to move this default into the database, that way we
    # make it less likely that something does it incorrectly (since the
    # default would be to generate a random key). However, it appears the
    # PostgreSQL pgcrypto extension uses OpenSSL RAND_bytes if available
    # instead of urandom. This is less than optimal, and we would generally
    # prefer to just always use urandom. Thus we'll do this ourselves here
    # in our application.
    key = Column(LargeBinary, nullable=False, default=_generate_key)
