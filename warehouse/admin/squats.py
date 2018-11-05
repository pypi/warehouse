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

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy import orm, sql

from warehouse import db


class Squat(db.ModelBase):

    __tablename__ = "warehouse_admin_squat"

    id = Column(Integer, primary_key=True, nullable=False)
    created = Column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    squatter_name = Column(
        Text, ForeignKey("packages.name", onupdate="CASCADE", ondelete="CASCADE")
    )
    squattee_name = Column(
        Text, ForeignKey("packages.name", onupdate="CASCADE", ondelete="CASCADE")
    )
    squatter = orm.relationship("Project", foreign_keys=[squatter_name], lazy=False)
    squattee = orm.relationship("Project", foreign_keys=[squattee_name], lazy=False)
    reviewed = Column(Boolean, nullable=False, server_default=sql.false())
