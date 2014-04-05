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

from werkzeug.routing import Map, Rule

from warehouse.accounts.urls import urls as accounts_urls
from warehouse.packaging.urls import urls as packaging_urls
from warehouse.search.urls import urls as search_urls
from warehouse.legacy.urls import urls as legacy_urls


# Top level URL rules
urls = [
    Rule("/", methods=["GET"], endpoint="warehouse.views.index"),
]

# Extend the URL rules with our other applications
urls += accounts_urls + packaging_urls + search_urls + legacy_urls

# Map our urls
urls = Map(urls)
