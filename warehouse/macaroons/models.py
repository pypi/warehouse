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
    )

    # All of our Macaroons belong to a specific user, because a caveat-less
    # Macaroon should act the same as their password does, instead of as a
    # global permission to upload files.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Store some information about the Macaroon to give users some mechanism
    # to differentiate between them.
    description = Column(String(100), nullable=False)
    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    last_used = Column(DateTime, nullable=True)

    # We'll store the caveats that were added to the Macaroon during generation
    # to allow users to see in their management UI what the total possible
    # scope of their macaroon is.
    caveats = Column(JSONB, nullable=False, server_default=sql.text("'{}'"))

    # It might be better to move this default into the database, that way we
    # make it less likely that something does it incorrectly (since the
    # default would be to generate a random key). However, it appears the
    # PostgreSQL pgcrypto extension uses OpenSSL RAND_bytes if available
    # instead of urandom. This is less than optimal, and we would generally
    # prefer to just always use urandom. Thus we'll do this ourselves here
    # in our application.
    key = Column(LargeBinary, nullable=False, default=_generate_key)
