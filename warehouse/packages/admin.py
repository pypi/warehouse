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
from django.contrib import admin

from warehouse.packages.models import Project


class ProjectAdmin(admin.ModelAdmin):

    list_display = ["name", "normalized", "autohide", "hosting_mode"]
    list_filter = ["autohide", "hosting_mode"]
    fields = ["name", "normalized", "hosting_mode", "autohide", "bugtrack_url"]
    readonly_fields = ["normalized"]
    search_fields = ["name", "normalized"]


admin.site.register(Project, ProjectAdmin)
