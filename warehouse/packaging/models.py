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

import datetime

from collections import namedtuple

from six.moves import urllib_parse
from sqlalchemy.sql import and_, select, func

from warehouse import models
from warehouse.packaging.tables import (
    packages, releases, release_files, description_urls, journals,
)


Project = namedtuple("Project", ["name"])

FileURL = namedtuple("FileURL", ["filename", "url"])


class Model(models.Model):

    def all_projects(self):
        query = select([packages.c.name]).order_by(func.lower(packages.c.name))

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
            select([description_urls.c.url], distinct=description_urls.c.url)
            .where(description_urls.c.name == name)
            .order_by(
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
                        "/".join([
                            "../../packages",
                            r["python_version"],
                            r["name"][0],
                            r["name"],
                            r["filename"],
                        ]),
                        "#md5={}".format(r["md5_digest"]),
                    ),
                )
                for r in results
            ]

    def get_project_for_filename(self, filename):
        query = (
            select([release_files.c.name])
            .where(release_files.c.filename == filename)
        )

        with self.engine.connect() as conn:
            return Project(conn.execute(query).scalar())

    def get_filename_md5(self, filename):
        query = (
            select([release_files.c.md5_digest])
            .where(release_files.c.filename == filename)
        )

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_last_serial(self, name=None):
        query = select([func.max(journals.c.id)])

        if name is not None:
            query = query.where(journals.c.name == name)

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_project_versions(self, project):
        query = (
            select([releases.c.version])
            .where(releases.c.name == project)
            .order_by(releases.c._pypi_ordering.desc())
        )

        with self.engine.connect() as conn:
            return [r["version"] for r in conn.execute(query)]

    def get_release(self, project, version):
        query = (
            select([
                releases.c.name,
                releases.c.version,
                releases.c.author,
                releases.c.author_email,
                releases.c.maintainer,
                releases.c.maintainer_email,
                releases.c.home_page,
                releases.c.license,
                releases.c.summary,
                releases.c.description,
                releases.c.keywords,
                releases.c.platform,
                releases.c.download_url,
                releases.c.requires_python,
            ])
            .where(and_(
                releases.c.name == project,
                releases.c.version == version,
            ))
        )

        with self.engine.connect() as conn:
            return dict(conn.execute(query).first())

    def get_download_counts(self, project, precisions=None):
        def _make_key(precision, datetime, key):
            return "downloads:{}:{}:{}".format(
                precision[0],
                datetime.strftime(precision[1]),
                key,
            )

        if precisions is None:
            precisions = [
                ("hour", "%y-%m-%d-%H"),
                ("daily", "%y-%m-%d"),
            ]

        # Get the current utc time
        current = datetime.datetime.utcnow()

        # Get the download count for the last 24 hours (roughly)
        keys = [
            _make_key(
                precisions[0],
                current - datetime.timedelta(hours=x),
                project,
            )
            for x in range(25)
        ]
        last_1 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        # Get the download count for the last 7 days (roughly)
        keys = [
            _make_key(
                precisions[1],
                current - datetime.timedelta(days=x),
                project,
            )
            for x in range(8)
        ]
        last_7 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        # Get the download count for the last month (roughly)
        keys = [
            _make_key(
                precisions[1],
                current - datetime.timedelta(days=x),
                project,
            )
            for x in range(31)
        ]
        last_30 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        return {
            "last_day": last_1,
            "last_week": last_7,
            "last_month": last_30,
        }
