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

import mimetypes
import os.path
import re

from werkzeug.exceptions import NotFound
from werkzeug.security import safe_join
from werkzeug.wsgi import wrap_file

from warehouse.helpers import url_for
from warehouse.http import Response
from warehouse.utils import cache, render_response


def index(app, request):
    projects = app.models.packaging.all_projects()
    resp = render_response(
        app, request, "legacy/simple/index.html",
        projects=projects,
    )

    # Add a header that points to the last serial
    serial = app.models.packaging.get_last_serial()
    resp.headers["X-PyPI-Last-Serial"] = serial

    return resp


def project(app, request, project_name):
    # Get the real project name for this project
    project = app.models.packaging.get_project(project_name)

    if project is None:
        raise NotFound("{} does not exist".format(project_name))

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

    resp = render_response(
        app, request,
        "legacy/simple/detail.html",
        project=project,
        files=file_urls,
        project_urls=project_urls,
        externals=external_urls,
    )

    # Add a header that points to the last serial
    serial = app.models.packaging.get_last_serial(project.name)
    resp.headers.add("X-PyPI-Last-Serial", serial)

    # Add a Link header to point at the canonical URL
    can_url = url_for(
        request, "warehouse.legacy.simple.project",
        project_name=project.name,
        _force_external=True,
    )
    resp.headers.add("Link", can_url, rel="canonical")

    return resp


@cache("packages")
def package(app, request, path):
    # Get our filename and filepath from the request path
    filename = os.path.basename(path)
    filepath = safe_join(
        os.path.abspath(app.config.paths.packages),
        path
    )

    # If we cannot safely join the requested path with our directory
    #   return a 404
    if filepath is None:
        raise NotFound("{} was not found".format(filename))

    # Open the file and attempt to wrap in the wsgi.file_wrapper if it's
    #   available, otherwise read it directly.
    try:
        with open(filepath, "rb") as fp:
            data = wrap_file(request.environ, fp)
    except IOError:
        raise NotFound("{} was not found".format(filename))

    # Get the project name and normalize it
    project = app.models.packaging.get_project_for_filename(filename)
    normalized = re.sub("_", "-", project.name, re.I).lower()

    # Get the MD5 hash of the file
    content_md5 = app.models.packaging.get_filename_md5(filename)

    headers = {}

    # Add in additional headers if we're using Fastly
    if app.config.fastly:
        headers.update({
            "Surrogate-Key": " ".join([
                "package",
                "package~{}".format(normalized),
            ]),
        })

    # Look up the last serial for this file
    serial = app.models.packaging.get_last_serial(project.name)
    if serial is not None:
        headers["X-PyPI-Last-Serial"] = serial

    # Pass through the data directly to the response object
    resp = Response(
        data,
        headers=headers,
        mimetype=mimetypes.guess_type(filename)[0],
        direct_passthrough=True,
    )

    # Setup the Last-Modified header
    resp.last_modified = os.path.getmtime(filepath)

    # Setup the Content-MD5 headers
    resp.content_md5 = content_md5

    # Setup Conditional Responses
    resp.set_etag(content_md5)
    resp.make_conditional(request)

    return resp
