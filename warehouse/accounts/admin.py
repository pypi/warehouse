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
from django.utils.translation import ugettext_lazy as _

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from warehouse.accounts.forms import UserChangeForm
from warehouse.accounts.models import User, Email


class EmailInline(admin.TabularInline):
    model = Email
    extra = 0


class UserAdmin(BaseUserAdmin):

    form = UserChangeForm

    inlines = [
        EmailInline,
    ]

    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    list_display = ["username", "email", "name", "is_staff"]
    fieldsets = (
        (None, {"fields": ["username", "password"]}),
        (_("Personal info"), {"fields": ["name"]}),
        (_("Permissions"), {"fields": [
                                        "is_active",
                                        "is_staff",
                                        "is_superuser",
                                        "groups",
                                        "user_permissions",
        ]}),
        (_("Important dates"), {"fields": ["last_login", "date_joined"]}),
    )
    search_fields = ["username", "name", "emails__email"]


admin.site.register(User, UserAdmin)
