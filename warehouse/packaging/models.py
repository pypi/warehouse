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

from warehouse import models


packages = models.Table("packages",
    models.Column("name",
        models.UnicodeText(),
        primary_key=True,
        nullable=False,
    ),
    models.Column("stable_version", models.UnicodeText()),
    models.Column("normalized_name", models.UnicodeText()),
    models.Column("autohide",
        models.Boolean(),
        server_default=models.sql.true(),
    ),
    models.Column("comments",
        models.Boolean(),
        server_default=models.sql.true(),
    ),
    models.Column("bugtrack_url", models.UnicodeText()),
    models.Column("hosting_mode",
        models.UnicodeText(),
        nullable=False,
        server_default="pypi-explicit",
    ),

    # Validate that packages begin and end with an alpha numeric and contain
    #   only alpha numeric, ., _, and -.
    models.CheckConstraint(
        "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
        name="packages_valid_name",
    ),
)
