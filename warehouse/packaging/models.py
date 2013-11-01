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
import os.path
import urlparse
import logging

from collections import namedtuple

from sqlalchemy.sql import and_, select, func
from sqlalchemy.sql.expression import false

from warehouse import models
from warehouse.accounts.tables import users, emails
from warehouse.packaging.tables import ReleaseDependencyKind
from warehouse.packaging.tables import (
    packages, releases, release_files, description_urls, journals,
    classifiers, release_classifiers, release_dependencies, roles
)

log = logging.getLogger(__name__)

Project = namedtuple("Project", ["name"])

FileURL = namedtuple("FileURL", ["filename", "url"])


class Model(models.Model):

    def get_project_count(self):
        query = select([func.count()]).select_from(packages)

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_download_count(self):
        query = select([func.sum(release_files.c.downloads)])

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_recently_updated(self, num=10):
        subquery = (
            select(
                [
                    releases.c.name,
                    releases.c.version,
                    releases.c.summary,
                    releases.c.created,
                ],
                distinct=releases.c.name,
            )
            .where(
                # We only consider releases made in the last 7 days, otherwise
                #   we have to do a Sequence Scan against the entire table
                #   and it takes 5+ seconds to complete. This shouldn't be a
                #   big deal as it is highly unlikely we'll have a week without
                #   at least 10 releases.
                releases.c.created >= (
                    datetime.datetime.utcnow() - datetime.timedelta(days=7)
                )
            )
            .order_by(releases.c.name, releases.c.created.desc())
            .alias("r")
        )

        query = (
            select("*")
            .select_from(subquery)
            .order_by(subquery.c.created.desc())
            .limit(num)
        )

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query)]

    def all_projects(self):
        query = select([packages.c.name]).order_by(func.lower(packages.c.name))

        with self.engine.connect() as conn:
            return [Project(r["name"]) for r in conn.execute(query)]

    def get_top_projects(self, num=None):
        query = (
            select([release_files.c.name, func.sum(release_files.c.downloads)])
            .group_by(release_files.c.name)
            .order_by(func.sum(release_files.c.downloads).desc())
        )
        if num:
            query = query.limit(num)

        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(query)]

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

    def get_projects_for_user(self, username):
        query = """
            SELECT DISTINCT ON (lower(name)) name, summary
            FROM (
                SELECT package_name
                FROM roles
                WHERE user_name = %(username)s
            ) roles
            INNER JOIN (
                SELECT name, summary
                FROM releases
                ORDER BY _pypi_ordering DESC
            ) releases
            ON (releases.name = roles.package_name)
            ORDER BY lower(name);
        """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, username=username)]

    def get_users_for_project(self, project):
        query = (
            select(
                [users.c.username, emails.c.email],
                from_obj=users.outerjoin(
                    emails, emails.c.user_id == users.c.id,
                ),
            )
            .where(and_(
                users.c.username == roles.c.user_name,
                roles.c.package_name == project,
            ))
            .order_by(
                roles.c.role_name.desc(),
                func.lower(roles.c.user_name),
            )
        )

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query)]

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
                    url=urlparse.urljoin(
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

    def get_projects_with_serial(self):
        # return list of dict(name: max id)
        query = (
            select([journals.c.name, func.max(journals.c.id)])
            .group_by(journals.c.name)
        )

        with self.engine.connect() as conn:
            return dict(r for r in conn.execute(query))

    def get_project_versions(self, project, show_hidden=False):
        query = (
            select([releases.c.version])
            .where(releases.c.name == project)
        )

        if not show_hidden:
            query = query.where(releases.c._pypi_hidden == false())

        query = query.order_by(releases.c._pypi_ordering.desc())

        with self.engine.connect() as conn:
            return [r["version"] for r in conn.execute(query)]

    def get_downloads(self, project, version):
        query = (
            select([
                release_files.c.name,
                release_files.c.version,
                release_files.c.python_version,
                release_files.c.packagetype,
                release_files.c.comment_text,
                release_files.c.filename,
                release_files.c.md5_digest,
                release_files.c.downloads,
                release_files.c.upload_time,
            ])
            .where(and_(
                release_files.c.name == project,
                release_files.c.version == version,
            ))
            .order_by(
                release_files.c.packagetype,
                release_files.c.python_version,
                release_files.c.upload_time,
            )
        )

        results = []
        with self.engine.connect() as conn:
            for r in conn.execute(query):
                result = dict(r)
                result["filepath"] = os.path.join(
                    self.app.config.paths.packages,
                    result["python_version"],
                    result["name"][0],
                    result["name"],
                    result["filename"],
                )
                if not os.path.exists(result["filepath"]):
                    log.error(
                        "%s missing for package %s %s",
                        result["filepath"],
                        result["name"],
                        result["version"])
                    continue
                result["url"] = "/".join([
                    "/packages",
                    result["python_version"],
                    result["name"][0],
                    result["name"],
                    result["filename"],
                ])
                result["size"] = os.path.getsize(result["filepath"])

                if os.path.exists(result["filepath"] + ".asc"):
                    result["pgp_url"] = result["url"] + ".asc"
                else:
                    result["pgp_url"] = None

                results.append(result)

        return results

    def get_release(self, project, version):
        query = (
            select([
                releases.c.name,
                releases.c.version,
                packages.c.stable_version,
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
                releases.c.created,
            ])
            .where(and_(
                releases.c.name == project,
                releases.c.version == version,
            ))
            .where(packages.c.name == project)
            .order_by(releases.c._pypi_ordering.desc())
            .limit(1)
        )

        with self.engine.connect() as conn:
            result = [dict(r) for r in conn.execute(query)][0]

        # Load dependency information
        query = (
            select([
                release_dependencies.c.name,
                release_dependencies.c.version,
                release_dependencies.c.kind,
                release_dependencies.c.specifier,
            ])
            .where(and_(
                release_dependencies.c.name == project,
                release_dependencies.c.version == version,
            ))
            .order_by(
                release_dependencies.c.kind,
                release_dependencies.c.specifier,
            )
        )

        dependency_data = {}
        with self.engine.connect() as conn:
            for dependency in conn.execute(query):
                kind = ReleaseDependencyKind(dependency["kind"])

                if kind in {
                        ReleaseDependencyKind.requires_dist,
                        ReleaseDependencyKind.provides_dist,
                        ReleaseDependencyKind.obsoletes_dist}:
                    value = dependency_data.setdefault(kind.name, [])
                    value.append(dependency["specifier"])

                if kind is ReleaseDependencyKind.project_url:
                    value = dependency_data.setdefault(kind.name, {})
                    value.update(dict([dependency["specifier"].split(",", 1)]))
        result.update(dependency_data)

        return result

    def get_releases(self, project):
        # Get the release data
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
                releases.c.keywords,
                releases.c.platform,
                releases.c.download_url,
                releases.c.created,
            ])
            .where(releases.c.name == project)
            .order_by(releases.c._pypi_ordering.desc())
        )

        with self.engine.connect() as conn:
            results = [dict(r) for r in conn.execute(query)]

        return results

    def get_download_counts(self, project):
        def _make_key(precision, datetime, key):
            return "downloads:{}:{}:{}".format(
                precision[0],
                datetime.strftime(precision[1]),
                key,
            )

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

    def get_classifiers(self, project, version):
        query = (
            select([classifiers.c.classifier])
            .where(and_(
                release_classifiers.c.name == project,
                release_classifiers.c.version == version,
                release_classifiers.c.trove_id == classifiers.c.id,
            ))
            .order_by(classifiers.c.classifier)
        )

        with self.engine.connect() as conn:
            return [r["classifier"] for r in conn.execute(query)]

    def get_documentation_url(self, project):
        path_parts = [
            self.app.config.paths.documentation,
            project,
            "index.html",
        ]
        if os.path.exists(os.path.join(*path_parts)):
            return urlparse.urljoin(
                self.app.config.urls.documentation,
                project
            ) + "/"

    def get_bugtrack_url(self, project):
        query = (
            select([packages.c.bugtrack_url])
            .where(packages.c.name == project)
        )

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()
