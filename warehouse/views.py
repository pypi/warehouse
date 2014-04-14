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
from flask import Blueprint, render_template, current_app as app
from warehouse.utils import cache

blueprint = Blueprint('warehouse.views', __name__)


@blueprint.route('/')
@cache(browser=1, varnish=120)
def index():
    return render_template(
        "index.html",
        project_count=app.db.packaging.get_project_count(),
        download_count=app.db.packaging.get_download_count(),
        recently_updated=app.db.packaging.get_recently_updated(),
    )
