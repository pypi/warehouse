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

from citext import CIText
from sqlalchemy import (
    Table, Column, CheckConstraint, ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy import Boolean, DateTime, Integer, String, Unicode
from sqlalchemy import sql

from warehouse.application import Warehouse


users = Table(
    "accounts_user",
    Warehouse.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("password", String(length=128), nullable=False),
    Column("last_login", DateTime(timezone=True), nullable=False),
    Column("is_superuser", Boolean(), nullable=False),
    Column("username", CIText(), nullable=False, unique=True),
    Column("name", Unicode(length=100), nullable=False),
    Column("is_staff", Boolean(), nullable=False),
    Column("is_active", Boolean(), nullable=False),
    Column(
        "date_joined",
        DateTime(timezone=True),
        server_default=sql.func.now(),
    ),

    CheckConstraint("length(username) <= 50", name="packages_valid_name"),
    CheckConstraint(
        "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
        name="accounts_user_valid_username",
    ),
)

emails = Table(
    "accounts_email",
    Warehouse.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("user_id",
        Integer(),
        ForeignKey("accounts_user.id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    ),
    Column("email", Unicode(length=254), nullable=False),
    Column("primary", Boolean(), nullable=False),
    Column("verified", Boolean(), nullable=False),

    UniqueConstraint("email", name="accounts_email_email_key"),

    Index("accounts_email_email_like", "email"),
    Index("accounts_email_user_id", "user_id"),
)
