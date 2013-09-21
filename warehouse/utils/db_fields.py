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
from django import forms
from django.core import validators
from django.db import connections
from django.db.models import fields
from django.utils.translation import ugettext_lazy as _

from south.modelsinspector import add_introspection_rules


def install_citext(sender, db, **kwargs):
    cursor = connections[db].cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS citext")


class CaseInsensitiveCharField(fields.CharField):
    # NOTE: You MUST manually add a CHECK CONSTRAINT to the database for
    #           max_length to be respected in the DB.

    def db_type(self, connection):
        return "citext"


class CaseInsensitiveTextField(fields.TextField):

    def db_type(self, connection):
        return "citext"


class URLTextField(fields.TextField):
    default_validators = [validators.URLValidator()]
    description = _("URL")

    def db_type(self, connection):
        return "text"

    def formfield(self, **kwargs):
        # As with CharField, this will cause URL validation to be performed
        # twice.
        defaults = {
            'form_class': forms.URLField,
        }
        defaults.update(kwargs)
        return super(URLTextField, self).formfield(**defaults)


add_introspection_rules([],
    ["^warehouse\.utils\.db_fields\.CaseInsensitiveCharField"],
)
add_introspection_rules([],
    ["^warehouse\.utils\.db_fields\.CaseInsensitiveTextField"],
)
add_introspection_rules([],
    ["^warehouse\.utils\.db_fields\.URLTextField"],
)
