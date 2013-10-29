# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

from sqlalchemy.sql import select, and_

from warehouse import models
from warehouse.accounts.tables import users, emails


class Model(models.Model):

    def get_user(self, name):
        query = (
            select([
                users.c.username,
                users.c.name,
                users.c.date_joined,
                emails.c.email,
            ])
            .where(and_(
                emails.c.user_id == users.c.id,
                users.c.username == name,
            ))
            .limit(1)
        )

        with self.engine.connect() as conn:
            result = conn.execute(query).first()

            if result is not None:
                result = dict(result)

            return result
