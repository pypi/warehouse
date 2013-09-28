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

from collections import namedtuple

from six.moves import urllib_parse
from sqlalchemy.sql import select, func

from warehouse import models
from warehouse.packaging.tables import (
    packages, releases, release_files, description_urls,
)


Project = namedtuple("Project", ["name"])

FileURL = namedtuple("FileURL", ["filename", "url"])


class Model(models.Model):

    def all_projects(self):
        query = select([packages.c.name]).order_by(packages.c.name)

        with self.engine.connect() as conn:
            return [Project(r["name"]) for r in conn.execute(query)]

    def get_project(self, name):
        query = (
            select([packages.c.name])
            .where(
                packages.c.normalized_name == func.lower(
                    func.regexp_replace(name, "_", "-", "ig"),
                )
            )
        )

        with self.engine.connect() as conn:
            result = conn.execute(query).scalar()

            if result is not None:
                return Project(result)

    def get_hosting_mode(self, name):
        query = (
            select([packages.c.hosting_mode])
            .where(packages.c.name == name)
        )

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_release_urls(self, name):
        query = (
            select([
                releases.c.version,
                releases.c.home_page,
                releases.c.download_url,
            ])
            .where(releases.c.name == name)
            .order_by(releases.c.version.desc())
        )

        with self.engine.connect() as conn:
            return {
                r["version"]: (r["home_page"], r["download_url"])
                for r in conn.execute(query)
            }

    def get_external_urls(self, name):
        query = (
            select([description_urls.c.url])
            .where(description_urls.c.name == name)
            .order_by(
                description_urls.c.version.desc(),
                description_urls.c.url,
            )
        )

        with self.engine.connect() as conn:
            return [r["url"] for r in conn.execute(query)]

    def get_file_urls(self, name):
        query = (
            select([
                release_files.c.name,
                release_files.c.filename,
                release_files.c.python_version,
                release_files.c.md5_digest,
            ])
            .where(release_files.c.name == name)
            .order_by(release_files.c.filename.desc())
        )

        with self.engine.connect() as conn:
            results = conn.execute(query)

            return [
                FileURL(
                    filename=r["filename"],
                    url=urllib_parse.urljoin(
                        os.path.join(
                            "../../packages",
                            r["python_version"],
                            r["name"][0],
                            r["name"],
                            r["filename"]
                        ),
                        "#md5={}".format(r["md5_digest"]),
                    ),
                )
                for r in results
            ]
