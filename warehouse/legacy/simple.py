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

import os.path

from sqlalchemy import sql
from werkzeug.exceptions import NotFound
from werkzeug.wrappers import Response


def index(app, request):
    query = (
        sql.select([app.tables["packages"].c.name])
           .order_by(app.tables["packages"].c.name)
    )
    template = app.templates.get_template("legacy/simple/index.html")

    results = app.connection.execute(query)
    try:
        return Response(
            template.render(projects=(r[0] for r in results)),
            content_type="text/html",
        )
    finally:
        results.close()


def project(app, request, project):
    packages = app.tables["packages"]
    releases = app.tables["releases"]
    release_files = app.tables["release_files"]
    description_urls = app.tables["description_urls"]

    file_urls, project_urls, external_urls = [], [], []

    # Get the real project name for this project
    query = (
        sql.select([packages.c.name])
            .where(
                packages.c.normalized_name == sql.func.lower(
                    sql.func.regexp_replace(project, "_", "-", "ig"),
                )
        )
    )
    project = app.connection.execute(query).scalar()

    # If the project doesn't exist we should raise a 404
    if project is None:
        raise NotFound("{} does not exist".format(project))

    # Generate the Package URLs for the packages we've hosted
    query = (
        sql.select([
            release_files.c.name,
            release_files.c.filename,
            release_files.c.python_version,
            release_files.c.md5_digest,
        ])
        .where(release_files.c.name == project)
        .order_by(release_files.c.filename.desc())
    )
    results = app.connection.execute(query)

    file_urls = [
        {
            "name": r["filename"],
            "url": os.path.join(
                "../../packages",
                r["python_version"],
                r["name"][0],
                r["name"],
                r["filename"]
            ) + "#md5={}".format(r["md5_digest"]),
        }
        for r in results
    ]

    # Determine what the hosting mode is for this package
    query = (
        sql.select([packages.c.hosting_mode])
           .where(packages.c.name == project)
    )
    results = app.connection.execute(query)
    hosting_mode = results.scalar()

    if hosting_mode in {"pypi-scrape-crawl", "pypi-scrape"}:
        rel_prefix = "" if hosting_mode == "pypi-scrape-crawl" else "ext-"
        home_rel = "{}homepage".format(rel_prefix)
        download_rel = "{}download".format(rel_prefix)

        # Generate the Homepage and Download URL links
        query = (
            sql.select([
                releases.c.version,
                releases.c.home_page,
                releases.c.download_url,
            ])
            .where(releases.c.name == project)
            .order_by(releases.c.version.desc())
        )
        results = app.connection.execute(query)

        for version, home_page, download_url in results:
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
    query = (
        sql.select([description_urls.c.url])
           .where(description_urls.c.name == project)
           .order_by(description_urls.c.version.desc(), description_urls.c.url)
    )
    external_urls = [r["url"] for r in app.connection.execute(query)]

    template = app.templates.get_template("legacy/simple/detail.html")
    return Response(
        template.render(
            project=project,
            files=file_urls,
            project_urls=project_urls,
            externals=external_urls,
        ),
        content_type="text/html",
    )
