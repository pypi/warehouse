# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import re

from django.core import validators
from django.db import models
from django.utils.translation import ugettext_lazy as _

from warehouse.utils.db_fields import CaseInsensitiveTextField


class Project(models.Model):

  # TODO: Add a DB CONSTRAINT for Project.name regex
  # TODO: Figure out how best to expose the normalized_name without duplicating
  # TODO: Migrate bugtrack_url to something that does not have a length limit

    name = CaseInsensitiveTextField(_("Name"),
        unique=True,
        help_text=_("Letters, digits, and ./-/_ only."),
        validators=[
            validators.RegexValidator(
                re.compile(r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.I),
                _("Must start and end with a letter or digit and may only "
                  "contain letters, digits, and ./-/_"),
                "invalid",
            ),
        ],
    )

    # TODO: Once PyPI legacy is gone we should remove this as it's not a very
    #   useful construct with a proper UX.
    autohide = models.BooleanField(_("Automatically hide old releases"),
        default=True,
    )

    # TODO: Once PyPI legacy is gone we should move this somewhere better.
    bugtrack_url = models.URLField(_("Bug Tracker URL"), blank=True)

    hosting_mode = models.CharField(_("Hosting mode"),
        choices=[
            ("pypi-explicit", _("Explicit URLs only")),
            ("pypi-scrape", _("Directly linked URLs from the description")),
            ("pypi-scrape-crawl", _("All possible URLs, including those that "
                                    "require offsite scraping (slow).")),
        ],
        default="pypi-explicit",
        max_length=20,
    )
