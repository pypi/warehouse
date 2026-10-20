# SPDX-License-Identifier: Apache-2.0

import datetime as dt

from typing import Annotated

from sqlalchemy import DateTime, TypeDecorator, sql
from sqlalchemy.orm import mapped_column

# Custom Types for SQLAlchemy Columns `Mapped` values
bool_false = Annotated[bool, mapped_column(server_default=sql.false())]
bool_true = Annotated[bool, mapped_column(server_default=sql.true())]
datetime_now = Annotated[dt.datetime, mapped_column(server_default=sql.func.now())]


class TZDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo:
            value = value.astimezone(dt.UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=dt.UTC)
        return value
