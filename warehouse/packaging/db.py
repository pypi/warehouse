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
import urllib.parse
import logging

from warehouse import db
from warehouse.packaging.tables import ReleaseDependencyKind


log = logging.getLogger(__name__)


class Database(db.Database):

    get_project_count = db.scalar(
        "SELECT COUNT(*) FROM packages"
    )

    get_download_count = db.scalar(
        "SELECT SUM(downloads) FROM release_files",
        default=0,
    )

    get_recently_updated = db.rows(
        # We only consider releases made in the last 7 days, otherwise we have
        # to do a Sequence Scan against the entire table and it takes 5+
        # seconds to complete. This shouldn't be a big deal as it is highly
        # unlikely we'll have a week without at least 10 releases.
        """ SELECT *
            FROM (
                SELECT DISTINCT ON (name) name, version, summary, created
                FROM releases
                WHERE created >= now() - interval '7 days'
                ORDER BY name, created DESC
            ) r
            ORDER BY r.created DESC
            LIMIT 10
        """
    )

    get_recent_projects = db.rows(
        # We only consider projects registered in the last 7 days (see
        # get_recently_updated for reasoning)
        """ SELECT
                p.name, r.version, p.created, r.summary
            FROM releases r, (
                SELECT packages.name, max_order, packages.created
                FROM packages
                JOIN (
                   SELECT name, max(_pypi_ordering) AS max_order
                     FROM releases
                    WHERE created >= now() - interval '7 days'
                    GROUP BY name
                ) mo ON packages.name = mo.name
            ) p
            WHERE p.name = r.name
              AND p.max_order = r._pypi_ordering
              AND p.created >= now() - interval '7 days'
            ORDER BY p.created DESC
            LIMIT %(num)s
        """
    )

    get_releases_since = db.rows(
        """ SELECT name, version, created, summary
            FROM releases
            WHERE created > %s
            ORDER BY created DESC
        """
    )

    get_changed_since = db.rows(
        """ SELECT name, max(submitted_date) FROM journals
            WHERE submitted_date > %s
            GROUP BY name
            ORDER BY max(submitted_date) DESC
        """,
        row_func=lambda r: r[0]
    )

    all_projects = db.rows(
        "SELECT name FROM packages ORDER BY lower(name)",
        row_func=lambda r: r["name"]
    )

    def get_top_projects(self, num=None):
        query = \
            """ SELECT name, sum(downloads)
                FROM release_files
                GROUP BY name
                ORDER BY sum(downloads) DESC
            """
        if num:
            query += "LIMIT %(limit)s"

        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(query, limit=num)]

    get_project = db.scalar(
        """ SELECT name
            FROM packages
            WHERE normalized_name = lower(
                regexp_replace(%s, '_', '-', 'ig')
            )
        """
    )

    get_projects_for_user = db.rows(
        """ SELECT DISTINCT ON (lower(name)) name, summary
            FROM (
                SELECT package_name
                FROM roles
                WHERE user_name = %s
            ) roles
            INNER JOIN (
                SELECT name, summary
                FROM releases
                ORDER BY _pypi_ordering DESC
            ) releases
            ON (releases.name = roles.package_name)
            ORDER BY lower(name)
        """
    )

    get_users_for_project = db.rows(
        """ SELECT DISTINCT ON (u.username) u.username, u.email
            FROM (
                SELECT username, email
                FROM accounts_user
                LEFT OUTER JOIN accounts_email ON (
                    accounts_email.user_id = accounts_user.id
                )
            ) u
            INNER JOIN roles ON (u.username = roles.user_name)
            WHERE roles.package_name = %s
        """
    )

    get_roles_for_project = db.rows(
        """ SELECT user_name, role_name
            FROM roles
            WHERE package_name = %s
            ORDER BY role_name, user_name
        """
    )

    get_roles_for_user = db.rows(
        """ SELECT package_name, role_name
            FROM roles
            WHERE user_name = %s
            ORDER BY package_name, role_name
        """
    )

    get_hosting_mode = db.scalar(
        "SELECT hosting_mode FROM packages WHERE name = %s"
    )

    get_release_urls = db.mapping(
        """ SELECT version, home_page, download_url
            FROM releases
            WHERE name = %s
            ORDER BY version DESC
        """,
        key_func=lambda r: r["version"],
        value_func=lambda r: (r["home_page"], r["download_url"]),
    )

    get_external_urls = db.rows(
        """ SELECT DISTINCT ON (url) url
            FROM description_urls
            WHERE name = %s
            ORDER BY url
        """,
        row_func=lambda r: r["url"]
    )

    get_file_urls = db.rows(
        """ SELECT name, filename, python_version, md5_digest
            FROM release_files
            WHERE name = %s
            ORDER BY filename DESC
        """,
        lambda r: {
            "filename": r["filename"],
            "url": urllib.parse.urljoin(
                "/".join([
                    "../../packages",
                    r["python_version"],
                    r["name"][0],
                    r["name"],
                    r["filename"],
                ]),
                "#md5={}".format(r["md5_digest"]),
            ),
        }
    )

    get_project_for_filename = db.scalar(
        "SELECT name FROM release_files WHERE filename = %s"
    )

    get_filename_md5 = db.scalar(
        "SELECT md5_digest FROM release_files WHERE filename = %s"
    )

    def get_last_serial(self, name=None):
        if name is not None:
            query = "SELECT MAX(id) FROM journals WHERE name = %(name)s"
        else:
            query = "SELECT MAX(id) FROM journals"

        return db.scalar(query)(self, name=name)

    get_projects_with_serial = db.mapping(
        "SELECT name, max(id) FROM journals GROUP BY name",
    )

    get_project_versions = db.rows(
        """ SELECT version
            FROM releases
            WHERE name = %s
            ORDER BY _pypi_ordering DESC
        """,
        row_func=lambda r: r["version"]
    )

    def get_downloads(self, project, version):
        query = \
            """ SELECT
                    name, version, python_version, packagetype, comment_text,
                    filename, md5_digest, downloads, upload_time
                FROM release_files
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY packagetype, python_version, upload_time
            """

        results = []
        with self.engine.connect() as conn:
            for r in conn.execute(query, project=project, version=version):
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
        query = \
            """ SELECT
                    name, version, author, author_email, maintainer,
                    maintainer_email, home_page, license, summary, description,
                    keywords, platform, download_url, created
                FROM releases
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY _pypi_ordering DESC
                LIMIT 1
            """

        with self.engine.connect() as conn:
            result = [
                dict(r)
                for r in conn.execute(query, project=project, version=version)
            ][0]

        # Load dependency information
        query = \
            """ SELECT name, version, kind, specifier
                FROM release_dependencies
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY kind, specifier
            """

        dependency_data = {}
        with self.engine.connect() as conn:
            for dependency in conn.execute(
                    query,
                    project=project,
                    version=version):
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

    get_releases = db.rows(
        """ SELECT
                name, version, author, author_email, maintainer,
                maintainer_email, home_page, license, summary, keywords,
                platform, download_url, created
            FROM releases
            WHERE name = %s
            ORDER BY _pypi_ordering DESC
        """
    )

    get_full_latest_releases = db.rows(
        """ SELECT DISTINCT ON (name)
                name, version, author, author_email, maintainer,
                maintainer_email, home_page, license, summary, description,
                keywords, platform, download_url, created
            FROM releases
            ORDER BY name, _pypi_ordering DESC
        """
    )

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

    get_classifiers = db.rows(
        """ SELECT classifier
            FROM release_classifiers
            INNER JOIN trove_classifiers ON (
                release_classifiers.trove_id = trove_classifiers.id
            )
            WHERE name = %s AND version = %s
            ORDER BY classifier
        """,
        row_func=lambda r: r["classifier"]
    )

    def get_classifier_ids(self, classifiers):
        query = \
            """ SELECT classifier, id
                FROM trove_classifiers
                WHERE classifier IN %(classifiers)s
            """

        with self.engine.connect() as conn:
            return {
                r["classifier"]: r["id"]
                for r in conn.execute(query, classifiers=tuple(classifiers))
            }

    def search_by_classifier(self, selected_classifiers):
        # Note: selected_classifiers is a list of ids from trove_classifiers
        if not selected_classifiers:
            return []

        # generate trove id -> level mapping
        trove = {}
        query = "SELECT * FROM trove_classifiers"
        with self.engine.connect() as conn:
            for id, classifier, l2, l3, l4, l5 in conn.execute(query):
                if id == l2:
                    trove[id] = 2
                elif id == l3:
                    trove[id] = 3
                elif id == l4:
                    trove[id] = 4
                else:
                    trove[id] = 5

        # compute a statement to produce all packages selected
        query = "SELECT name, version FROM releases"
        for c in selected_classifiers:
            level = trove[c]
            query = \
                """ SELECT DISTINCT a.name, a.version
                    FROM (%s) a, release_classifiers rc, trove_classifiers t
                    WHERE a.name=rc.name
                    AND a.version=rc.version
                    AND rc.trove_id=t.id
                    AND t.l%d=%d
                """ % (query, level, c)

        releases = []
        with self.engine.connect() as conn:
            for name, version in conn.execute(query):
                releases.append((name, version))

        return releases

    def get_documentation_url(self, project):
        path_parts = [
            self.app.config.paths.documentation,
            project,
            "index.html",
        ]
        if os.path.exists(os.path.join(*path_parts)):
            return urllib.parse.urljoin(
                self.app.config.urls.documentation,
                project
            ) + "/"

    get_bugtrack_url = db.scalar(
        "SELECT bugtrack_url FROM packages WHERE name = %s"
    )

    get_changelog = db.rows(
        """ SELECT name, version, submitted_date, action, id
            FROM journals
            WHERE journals.submitted_date > %s
            ORDER BY submitted_date DESC
        """
    )

    get_last_changelog_serial = db.scalar(
        "SELECT max(id) FROM journals"
    )

    get_changelog_serial = db.rows(
        """ SELECT name, version, submitted_date, action, id
            FROM journals
            WHERE journals.id > %s
            ORDER BY submitted_date DESC
        """
    )
