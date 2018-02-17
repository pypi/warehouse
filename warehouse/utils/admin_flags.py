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

from sqlalchemy import Column, Boolean, Text

from warehouse import db


class AdminFlag(db.Model):

    __tablename__ = "warehouse_admin_flag"

    id = Column(Text, primary_key=True, nullable=False)
    description = Column(Text, nullable=False)
    enabled = Column(Boolean)

    @classmethod
    def is_enabled(cls, session, flag_name):
        flag = (session.query(AdminFlag)
                       .filter(AdminFlag.id == flag_name)
                       .first())
        if flag is None:
            return False
        return flag.enabled
