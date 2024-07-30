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
import datetime

from typing import Annotated

from sqlalchemy import DateTime, TypeDecorator, sql
from sqlalchemy.orm import mapped_column

# Custom Types for SQLAlchemy Columns `Mapped` values
bool_false = Annotated[bool, mapped_column(server_default=sql.false())]
bool_true = Annotated[bool, mapped_column(server_default=sql.true())]
datetime_now = Annotated[
    datetime.datetime, mapped_column(server_default=sql.func.now())
]


class TZDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo:
                value = value.astimezone(datetime.UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=datetime.UTC)
        return value
