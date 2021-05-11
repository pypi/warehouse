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

from sqlalchemy import Boolean, Column, String, sql
from sqlalchemy.types import PickleType

from warehouse import db
from warehouse.utils.attrs import make_repr


class Sponsor(db.Model):
    __tablename__ = "sponsors"
    __repr__ = make_repr("name")

    name = Column(String, nullable=False)
    service = Column(String, nullable=False)
    # activity should be a list of strings
    activity = Column(PickleType, nullable=False)

    url = Column(String, nullable=False)  # TODO use URL field
    color_logo_url = Column(String, nullable=False)  # TODO use URL field
    white_logo_url = Column(String)  # TODO use URL field

    # control flags
    footer = Column(Boolean, server_default=sql.false(), nullable=False)
    psf_sponsor = Column(Boolean, server_default=sql.false(), nullable=False)
    infra_sponsor = Column(Boolean, server_default=sql.false(), nullable=False)
    one_time = Column(Boolean, server_default=sql.false(), nullable=False)
    sidebar = Column(Boolean, server_default=sql.false(), nullable=False)
