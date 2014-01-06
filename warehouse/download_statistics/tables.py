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
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from sqlalchemy import (
    Table, Column, UnicodeText, Text, Enum, DateTime
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from warehouse import db


downloads = Table(
    "downloads", db.metadata,
    Column(
        "id",
        UUID(),
        primary_key=True,
        nullable=False,
        server_default=func.uuid_generate_v4()
    ),

    Column("package_name", UnicodeText(), nullable=False),
    Column("package_version", UnicodeText()),
    Column(
        "distribution_type",
        Enum("sdist", "wheel", "exe", "egg", "msi", name="distribution_type")
    ),

    Column(
        "python_type",
        Enum("cpython", "pypy", "jython", "ironpython", name="python_type")
    ),
    Column("python_release", Text()),
    Column("python_version", Text()),

    Column(
        "installer_type",
        Enum(
            "browser",
            "pip",
            "setuptools",
            "distribute",
            "bandersnatch",
            "z3c.pypimirror",
            "pep381client",
            "devpi",
            name="installer_type"
        )
    ),
    Column("installer_version", Text()),

    Column("operating_system", Text()),
    Column("operating_system_version", Text()),

    Column("download_time", DateTime(), nullable=False),
    Column("raw_user_agent", Text(), nullable=False),
)
