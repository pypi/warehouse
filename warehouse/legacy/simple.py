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

from werkzeug.exceptions import NotFound

from warehouse.utils import render_response


def index(app, request):
    projects = app.models.packaging.all_projects()
    return render_response(
        app, request, "legacy/simple/index.html",
        projects=projects,
    )


def project(app, request, project_name):
    # Get the real project name for this project
    project = app.models.packaging.get_project(project_name)

    if project is None:
        raise NotFound("{} does not exist".format(project.name))

    # Generate the Package URLs for the packages we've hosted
    file_urls = app.models.packaging.get_file_urls(project.name)

    # Determine what the hosting mode is for this package
    hosting_mode = app.models.packaging.get_hosting_mode(project.name)

    project_urls = []
    if hosting_mode in {"pypi-scrape-crawl", "pypi-scrape"}:
        rel_prefix = "" if hosting_mode == "pypi-scrape-crawl" else "ext-"
        home_rel = "{}homepage".format(rel_prefix)
        download_rel = "{}download".format(rel_prefix)

        # Generate the Homepage and Download URL links
        release_urls = app.models.packaging.get_release_urls(project.name)
        for version, (home_page, download_url) in release_urls:
            if home_page and home_page != "UNKNOWN":
                project_urls.append({
                    "rel": home_rel,
                    "url": home_page,
                    "name": "{} home_page".format(version),
                })

            if download_url and download_url != "UNKNOWN":
                project_urls.append({
                    "rel": download_rel,
                    "url": download_url,
                    "name": "{} download_url".format(version),
                })

    # Fetch the explicitly provided URLs
    external_urls = app.models.packaging.get_external_urls(project.name)

    return render_response(
        app, request,
        "legacy/simple/detail.html",
        project=project,
        files=file_urls,
        project_urls=project_urls,
        externals=external_urls,
    )
