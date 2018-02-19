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

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID

from warehouse import db


report_source = ENUM(
    'automation',
    'user',
    name="report_source_enum",
)


class SpamReport(db.Model):

    __tablename__ = "spam_report"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_name", "release_version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "reporter_user_id IS NOT NULL OR source = 'automation'",
            name="valid_reporter_user_id",
        ),
    )

    release_name = Column(Text, nullable=False)
    release_version = Column(Text, nullable=False)
    source = Column(report_source, nullable=False)
    reporter_user_id = Column(UUID, nullable=True)
    result = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    valid = Column(Boolean, nullable=True)
